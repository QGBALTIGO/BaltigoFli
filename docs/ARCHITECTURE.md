# Arquitetura

## Componentes

### Web
Dashboard estático servido por Nginx. O Nginx também faz proxy de `/api/*` para o FastAPI.

### API
Responsável por mídia, destinos RTMP, playlists e estado desejado das transmissões. Não mantém FFmpeg dentro do processo web.

### Worker
Reconcilia o banco em intervalos curtos. Para cada transmissão marcada como `running` e já vencida no agendamento, cria um processo FFmpeg. Se o processo cair, registra erro e aplica backoff exponencial antes de tentar novamente.

### Banco
PostgreSQL armazena metadados. Stream Keys são criptografadas em repouso usando uma chave derivada de `APP_SECRET`.

### Mídia
No MVP, mídia e logs vivem em um volume Docker compartilhado por API e worker. Para produção distribuída, migre vídeos para R2/S3 e use storage local apenas como cache do worker.

## Estados

- `stopped`: inativa;
- `scheduled`: aguardando horário;
- `starting`: worker iniciando FFmpeg;
- `live`: processo FFmpeg saudável;
- `recovering`: caiu e aguarda tentativa;
- `stopping`: parada solicitada.

`desired_state` é separado de `status`. Isso permite ao worker saber se uma queda deve resultar em reinício ou parada definitiva.

## Escala sugerida

```text
Web/API -> Postgres
        -> Redis queue
        -> Scheduler
        -> Worker node A -> FFmpeg
        -> Worker node B -> FFmpeg
        -> Worker node C -> FFmpeg
```

Cada worker deve anunciar capacidade (CPU, RAM, banda e número de slots) e receber streams por scheduler. Não rode dezenas de transcodificações no mesmo nó sem cgroups/containers e limites.
