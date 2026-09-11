# Segurança

## Implementado no MVP

- Stream Keys não são retornadas pela API;
- Stream Keys são criptografadas em repouso;
- chave administrativa obrigatória para endpoints operacionais;
- destino completo é removido dos logs exibidos pelo worker;
- nomes de arquivos enviados não são usados como caminho final no disco;
- extensões aceitas são limitadas;
- `ffprobe` valida o arquivo antes do cadastro.

## Obrigatório antes de SaaS público

1. autenticação por usuário e MFA opcional;
2. RBAC entre owner/admin/operator/viewer;
3. KMS/Vault para chaves de streaming;
4. HTTPS obrigatório e HSTS;
5. rate limit e proteção contra brute force;
6. limites de upload por plano;
7. antivírus/malware scanning para uploads;
8. isolamento de processos e filesystem por tenant;
9. auditoria de start/stop/delete/change destination;
10. rotação de credenciais;
11. backups do PostgreSQL;
12. políticas de retenção de mídia e logs;
13. CSP e headers de segurança no frontend;
14. não coletar senha/cookie de plataforma quando RTMP/OAuth oficial resolver o fluxo.

## Conteúdo e plataformas

O motor é genérico e deve ser usado respeitando as regras de cada destino. Não implemente mecanismos de evasão de moderação, anti-ban, falsificação de presença humana ou detecção de replay.
