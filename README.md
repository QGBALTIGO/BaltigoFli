# Baltigo Live Cloud

MVP de uma plataforma de transmissão em nuvem para publicar mídia própria/licenciada em destinos RTMP compatíveis.

> Este projeto não implementa bypass de moderação, anti-ban, falsificação de interação ao vivo nem mecanismos para contornar regras de plataformas. Use apenas conteúdo e modos de transmissão permitidos pelo destino escolhido.

## Recursos atuais

- dashboard web responsivo;
- upload e inspeção de vídeos com `ffprobe`;
- destinos RTMP com Stream Key criptografada em repouso;
- playlists ordenadas;
- live de vídeo único ou playlist;
- loop contínuo;
- início imediato e agendamento;
- worker FFmpeg separado da API;
- watchdog com reinício automático;
- logs por transmissão;
- PostgreSQL;
- Docker Compose;
- autenticação administrativa simples por `X-API-Key`.

## Arquitetura

```text
Navegador
   |
   v
Nginx (web) -- /api --> FastAPI ------> PostgreSQL
                              ^              ^
                              |              |
                              +-------- Worker FFmpeg
                                           |
                                           v
                                     RTMP destination
```

A API grava o estado desejado da transmissão. O worker é quem inicia, encerra e vigia o FFmpeg. Se ele reiniciar, reconstrói as transmissões que continuam marcadas como ativas.

## Subir com Docker

```bash
cp .env.example .env
# troque ADMIN_API_KEY, APP_SECRET e POSTGRES_PASSWORD
docker compose up --build -d
```

Acesse:

- painel: http://localhost:8080
- Swagger: http://localhost:8000/docs
- health: http://localhost:8000/health

No painel, informe o mesmo valor configurado em `ADMIN_API_KEY`.

## Fluxo

1. Envie um vídeo em **Mídia**.
2. Cadastre um destino em **Destinos** com Server URL + Stream Key fornecidos pela plataforma.
3. Opcionalmente monte uma **Playlist**.
4. Crie uma transmissão em **Lives**.
5. Clique em **Iniciar** ou defina um horário.
6. O worker mantém o FFmpeg e tenta recuperar quedas inesperadas.

## Formato recomendado

Para reduzir CPU no servidor, prepare os vídeos previamente em H.264/AAC, 1080x1920 ou 720x1280 e 30 FPS.

Com `STREAM_TRANSCODE=false`, o worker tenta apenas copiar os codecs (`-c copy`). Se o destino rejeitar o arquivo, habilite transcodificação no `.env`.

## Antes de abrir para clientes

Este repositório é um MVP administrável. Antes de virar SaaS público, implemente contas reais, RBAC, quotas, object storage S3/R2, fila distribuída, isolamento de workers, rate limit, auditoria, HTTPS, rotação de chaves e observabilidade.

Leia também `docs/ARCHITECTURE.md`, `docs/SECURITY.md` e `docs/ROADMAP.md`.
