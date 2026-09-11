# Roadmap

## Fase 1 — MVP (este repositório)

- biblioteca de vídeos;
- RTMP customizado;
- loop e playlists;
- agenda;
- watchdog;
- dashboard;
- logs.

## Fase 2 — operação real

- contas de usuário e organizações;
- migrations com Alembic;
- R2/S3;
- Redis + fila;
- scheduler de workers;
- métricas de bitrate/FPS/uptime;
- preview HLS/WebRTC com MediaMTX;
- notificações Telegram/email;
- quotas e cobrança.

## Fase 3 — integrações

- OAuth oficial das plataformas onde disponível;
- analytics oficiais;
- múltiplos destinos simultâneos;
- templates de cenas e overlays;
- API pública e webhooks;
- troca de playlist sem derrubar a live.

## Fase 4 — escala

- autoscaling de workers;
- GPU workers para transcodificação pesada;
- regiões múltiplas;
- failover de nó;
- SLA e painel de incidentes.
