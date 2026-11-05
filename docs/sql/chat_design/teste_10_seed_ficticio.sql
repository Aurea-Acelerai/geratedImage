insert into public.segmentos(id,nome) values ('00000000-0000-0000-0000-0000000000a1','Alimentação');
-- clientes fictícios (a..h); cpf/cnpj/email/telefone são falsos e NÃO podem aparecer
insert into public.clientes(id,nome,cpf,cnpj,nome_fantasia,email,telefone,segmento) values
 ('c0000000-0000-0000-0000-00000000000a','Empresa A Ltda',null,'11111111000111','Marca A','a@fake.test','11900000001','00000000-0000-0000-0000-0000000000a1'),
 ('c0000000-0000-0000-0000-00000000000b','Empresa B',null,'22222222000122',null,'b@fake.test','11900000002',null),
 ('c0000000-0000-0000-0000-00000000000c','Pessoa C','12345678901',null,null,'c@fake.test','11900000003',null),
 ('c0000000-0000-0000-0000-00000000000d','Empresa D',null,'44444444000144',null,'d@fake.test','1',null),
 ('c0000000-0000-0000-0000-00000000000e','Empresa E',null,'55555555000155',null,'e@fake.test','1',null),
 ('c0000000-0000-0000-0000-00000000000f','Empresa F',null,'66666666000166',null,'f@fake.test','1',null),
 ('c0000000-0000-0000-0000-000000000010','Empresa G sem doc',null,null,null,'g@fake.test','1',null),
 ('c0000000-0000-0000-0000-000000000011','Empresa H',null,'88888888000188',null,'h@fake.test','1',null),
 ('c0000000-0000-0000-0000-000000000012','Empresa 100% _x\y',null,'99999999000199',null,'i@fake.test','1',null);
-- compras: (a) assinada+paga entra; (b) so assinada fora; (b2) parcialmente_pago entra; (c) paga sem assinatura fora;
-- (d) cancelada fora; (e) recusada fora; (f) teste fora; (g) duas elegíveis -> a mais recente; (h) mais recente inelegível, vale a anterior
insert into public.compras(id,cliente_id,clicksign_status,checkout_status,vendaaprovada,cancelado,vendarecusada,is_test,created_at,valor) values
 ('b0000000-0000-0000-0000-00000000000a','c0000000-0000-0000-0000-00000000000a','Assinado','pago',null,null,false,false,'2026-01-01',1000),
 ('b0000000-0000-0000-0000-00000000000b','c0000000-0000-0000-0000-00000000000b','Assinado','aguardando_pagamento',null,null,false,false,'2026-01-01',1),
 ('b0000000-0000-0000-0000-00000000000c','c0000000-0000-0000-0000-00000000000c','Assinado','parcialmente_pago',null,null,false,false,'2026-01-01',1),
 ('b0000000-0000-0000-0000-00000000000d','c0000000-0000-0000-0000-00000000000d','Pendente','pago',null,null,false,false,'2026-01-01',1),
 ('b0000000-0000-0000-0000-00000000000e','c0000000-0000-0000-0000-00000000000e','Assinado','pago',null,'{"motivo":"x"}',false,false,'2026-01-01',1),
 ('b0000000-0000-0000-0000-00000000000f','c0000000-0000-0000-0000-00000000000f','Assinado','pago',null,null,true,false,'2026-01-01',1),
 ('b0000000-0000-0000-0000-000000000010','c0000000-0000-0000-0000-000000000010','Assinado','pago',null,null,false,true,'2026-01-01',1),
 ('b0000000-0000-0000-0000-000000000011','c0000000-0000-0000-0000-000000000011','Assinado','pago',null,null,false,false,'2026-01-01',1),
 ('b0000000-0000-0000-0000-000000000021','c0000000-0000-0000-0000-000000000011','Assinado','pago',null,null,false,false,'2026-03-01',1),
 ('b0000000-0000-0000-0000-000000000031','c0000000-0000-0000-0000-000000000012','Assinado','pago',null,null,false,false,'2026-01-01',1),
 ('b0000000-0000-0000-0000-000000000032','c0000000-0000-0000-0000-000000000012','Assinado','aguardando_pagamento',null,null,false,false,'2026-05-01',1);
insert into public.onboarding_identity(compra_id,brand_display_name,brand_palette,font_choice,site_url,instagram_handle,campaign_notes,campaign_images_paths) values
 ('b0000000-0000-0000-0000-00000000000a','Marca A Premium','{"#FF0000","vermelho","#00ff00","javascript:alert(1)"}','Inter','https://a.test','@a','SEGREDO-NOTA','{"b0000000-0000-0000-0000-00000000000a/ref1.png","../../etc/passwd","/abs/x.png"}');
insert into public.onboarding_briefings(compra_id,briefing_json,status,brief_text) values
 ('b0000000-0000-0000-0000-00000000000a','{"tom_voz":"Calorosa","publico_alvo":"Familias","mensagem_central":"Sabor de casa"}','done','SEGREDO-BRIEF');
insert into public.onboarding_logo_history(compra_id,logo_path,mime_type,size_bytes,is_active) values
 ('b0000000-0000-0000-0000-00000000000a','b0000000-0000-0000-0000-00000000000a/logo.png','image/png',1234,true),
 ('b0000000-0000-0000-0000-00000000000a','http://evil.test/x.png','image/png',1,false),
 ('b0000000-0000-0000-0000-00000000000a','b0000000-0000-0000-0000-00000000000a/../x.png','image/png',1,false);
insert into public."celebridadesReferencia"(id,nome,"fotoPrincipal","fotoMobile",ativo) values
 ('e0000000-0000-0000-0000-000000000001','Celebridade Ficticia Um','https://x.supabase.co/storage/v1/object/public/celebs/1.jpg',null,true),
 ('e0000000-0000-0000-0000-000000000002','Celebridade Inativa','https://x/2.jpg',null,false),
 ('e0000000-0000-0000-0000-000000000003','Celebridade Nula','https://x/3.jpg',null,null);
insert into public.compras_celebridades values ('b0000000-0000-0000-0000-00000000000a','e0000000-0000-0000-0000-000000000001',true),('b0000000-0000-0000-0000-00000000000a','e0000000-0000-0000-0000-000000000002',false),('b0000000-0000-0000-0000-00000000000a','e0000000-0000-0000-0000-000000000003',false);
