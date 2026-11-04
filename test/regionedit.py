#!/usr/bin/env python3
"""Edição localizada com máscara e recomposição do original por código (precisa de Pillow; sem Pillow o recurso se desliga).

Por que existe: ao editar uma peça pronta, o modelo de imagem REGENERA a imagem inteira e degrada o que devia ficar igual
(rótulos de embalagens, arco do selo, textos pequenos). Aqui o modelo só pode mexer numa região; depois recolamos o
ORIGINAL fora dela, então logo, rótulos e textos ficam idênticos por construção.

Dois modos:
- local:  uma ou mais caixas (a pessoa, um texto). Máscara com a região transparente; o resultado é colado só dentro da caixa.
- extend: estende o fundo para outro formato (ex.: feed 4:5 -> story 9:16). O original é colocado no centro, o modelo preenche
          o que sobra em cima e embaixo e o original volta pixel a pixel por cima.

Uso: python regionedit.py --self-test   (precisa de Pillow; ex.: test/.venv/bin/python)
"""
import base64, io, json, re, sys

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:  # sem Pillow o recurso fica indisponível, o resto do chat segue igual
    Image = ImageDraw = ImageFilter = None

LOCATE_SYSTEM = (
    "Você localiza regiões de uma imagem para uma edição localizada. Receberá a imagem e a instrução de edição. "
    "Responda SOMENTE JSON: {\"regions\":[{\"label\":\"<o que é>\",\"box\":[x0,y0,x1,y1]}]} com caixas NORMALIZADAS de 0 a 1 "
    "(origem no canto superior esquerdo; x para a direita, y para baixo). As caixas devem cobrir **somente** o que precisa mudar "
    "para cumprir a instrução, com cerca de 2% de margem, e **não** podem incluir elementos vizinhos que devem ficar iguais "
    "(logo, selos, textos vizinhos, embalagens de produtos, botões). Ex.: para trocar uma pessoa, a caixa cobre a pessoa; para "
    "trocar duas palavras de um título, uma caixa justa em volta de cada palavra. No máximo 6 caixas."
)


def available():
    return Image is not None


def parse_regions(text):
    """JSON do localizador -> lista de (label, (x0,y0,x1,y1)) normalizados e válidos. Levanta ValueError se nada servir."""
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0) if m else text)
    out = []
    for r in (data.get("regions") or [])[:6]:
        b = r.get("box")
        if not (isinstance(b, (list, tuple)) and len(b) == 4):
            continue
        x0, y0, x1, y1 = (min(1.0, max(0.0, float(v))) for v in b)
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        if (x1 - x0) >= 0.02 and (y1 - y0) >= 0.02:
            out.append((str(r.get("label", ""))[:60], (x0, y0, x1, y1)))
    if not out:
        raise ValueError("o localizador não devolveu nenhuma região válida")
    return out


def to_px(regions, w, h):
    return [(int(x0 * w), int(y0 * h), int(round(x1 * w)), int(round(y1 * h))) for _, (x0, y0, x1, y1) in regions]


def _png(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def open_rgb(data):
    return Image.open(io.BytesIO(data)).convert("RGB")


def local_mask_png(size, boxes_px):
    """RGBA: opaco = manter; transparente (alpha 0) dentro das caixas = onde o modelo pode editar."""
    m = Image.new("RGBA", size, (0, 0, 0, 255))
    d = ImageDraw.Draw(m)
    for b in boxes_px:
        d.rectangle(b, fill=(0, 0, 0, 0))
    return _png(m)


def composite_local(orig_bytes, gen_bytes, boxes_px, feather=6):
    """Original fora das caixas; imagem gerada dentro, com a borda suavizada. Tamanho final = tamanho do original."""
    o = open_rgb(orig_bytes)
    g = open_rgb(gen_bytes).resize(o.size, Image.LANCZOS)
    mask = Image.new("L", o.size, 0)
    d = ImageDraw.Draw(mask)
    for b in boxes_px:
        d.rectangle(b, fill=255)
    if feather:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
    return _png(Image.composite(g, o, mask))


def make_extend(orig_bytes, out_w, out_h):
    """Coloca o original centralizado numa tela maior. Devolve (tela_png, mascara_png, original_redimensionado_png, (x, y, w, h))."""
    o = open_rgb(orig_bytes)
    scale = min(out_w / o.width, out_h / o.height)
    nw, nh = round(o.width * scale), round(o.height * scale)
    r = o.resize((nw, nh), Image.LANCZOS)
    x, y = (out_w - nw) // 2, (out_h - nh) // 2
    canvas = Image.new("RGB", (out_w, out_h))
    if y > 0:  # contexto de cor para o modelo: estica a primeira e a última linha nas faixas vazias
        canvas.paste(r.crop((0, 0, nw, 1)).resize((out_w, y)), (0, 0))
        canvas.paste(r.crop((0, nh - 1, nw, nh)).resize((out_w, out_h - y - nh)), (0, y + nh))
    if x > 0:
        canvas.paste(r.crop((0, 0, 1, nh)).resize((x, out_h)), (0, 0))
        canvas.paste(r.crop((nw - 1, 0, nw, nh)).resize((out_w - x - nw, out_h)), (x + nw, 0))
    canvas.paste(r, (x, y))
    mask = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))  # transparente = pode editar (as faixas novas)
    ImageDraw.Draw(mask).rectangle((x, y, x + nw - 1, y + nh - 1), fill=(0, 0, 0, 255))
    return _png(canvas), _png(mask), _png(r), (x, y, nw, nh)


def composite_extend(gen_bytes, resized_orig_png, placement, size, feather=4):
    """A imagem gerada serve só para as faixas novas; o original redimensionado volta idêntico por cima."""
    g = open_rgb(gen_bytes).resize(size, Image.LANCZOS)
    x, y, w, h = placement
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rectangle((x, y, x + w - 1, y + h - 1), fill=255)
    if feather:
        inner = Image.new("L", size, 0)
        ImageDraw.Draw(inner).rectangle((x + feather, y + feather, x + w - 1 - feather, y + h - 1 - feather), fill=255)
        mask = inner.filter(ImageFilter.GaussianBlur(feather))
    layer = Image.new("RGB", size)
    layer.paste(open_rgb(resized_orig_png), (x, y))
    return _png(Image.composite(layer, g, mask))


def locate(chat_json, image_bytes, mime, instruction):
    """chat_json(system, user_text, data_url) -> texto da resposta. Devolve regiões normalizadas ou levanta ValueError."""
    url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
    return parse_regions(chat_json(LOCATE_SYSTEM, f"Instrução de edição: {instruction}", url))


def self_test():
    if not available():
        print("regionedit: Pillow ausente, autoteste pulado (use test/.venv/bin/python)")
        return
    regs = parse_regions('texto {"regions":[{"label":"a","box":[0.5,0.2,0.1,0.6]},{"label":"ruim","box":[0.3,0.3,0.3,0.3]},{"label":"c","box":[-1,0,2,0.5]}]} fim')
    assert len(regs) == 2 and regs[0][1] == (0.1, 0.2, 0.5, 0.6) and regs[1][1] == (0.0, 0.0, 1.0, 0.5), regs
    try:
        parse_regions('{"regions":[]}')
        raise AssertionError("deveria falhar")
    except ValueError:
        pass
    # local: fora da caixa = original; dentro = gerada
    orig = _png(Image.new("RGB", (200, 250), (200, 30, 30)))
    gen = _png(Image.new("RGB", (100, 125), (30, 30, 200)))
    boxes = to_px(regs[:1], 200, 250)  # (20,50,100,150)
    out = open_rgb(composite_local(orig, gen, boxes, feather=0))
    assert out.size == (200, 250) and out.getpixel((10, 10)) == (200, 30, 30) and out.getpixel((60, 100)) == (30, 30, 200), (out.size, out.getpixel((10, 10)), out.getpixel((60, 100)))
    mk = Image.open(io.BytesIO(local_mask_png((200, 250), boxes)))
    assert mk.mode == "RGBA" and mk.getpixel((10, 10))[3] == 255 and mk.getpixel((60, 100))[3] == 0
    # extend: 4:5 -> 2:3
    o2 = _png(Image.new("RGB", (1080, 1350), (10, 120, 10)))
    canvas, mask, rorig, pl = make_extend(o2, 1024, 1536)
    assert Image.open(io.BytesIO(canvas)).size == (1024, 1536) and pl == (0, 128, 1024, 1280), pl
    mm = Image.open(io.BytesIO(mask))
    assert mm.getpixel((500, 10))[3] == 0 and mm.getpixel((500, 700))[3] == 255
    final = open_rgb(composite_extend(_png(Image.new("RGB", (1024, 1536), (200, 0, 200))), rorig, pl, (1024, 1536), feather=0))
    assert final.size == (1024, 1536) and final.getpixel((500, 10)) == (200, 0, 200) and final.getpixel((500, 700)) == (10, 120, 10)
    print("regionedit self-test ok")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        print(__doc__)
