# Monitoramento de vencimentos

Backend multiempresa para ler planilhas Google Sheets, acompanhar documentos e treinamentos, e registrar notificações sem duplicidade no PostgreSQL/Supabase. A planilha é a interface operacional; o banco é a fonte confiável de histórico e idempotência.

## Arquitetura

`app/domain` contém regras puras de vencimento e normalização. `application` orquestra a sincronização. `infrastructure` concentra SQLAlchemy, Google Sheets e SMTP. Cada tabela de negócio é segmentada por `company_id`; consultas de funcionários, requisitos e eventos sempre passam pelo escopo da empresa.

Principais tabelas: `companies`, `employees`, `vehicles`, `requirement_types`, `requirement_records`, `notification_rules`, `notification_events` e `sync_executions`.

## Configuração local

Requer Python 3.12+ e PostgreSQL (ou SQLite somente para desenvolvimento/testes).

```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
alembic upgrade head
python -m app.infrastructure.database.seed
uvicorn app.main:app --reload --port 10000
```

Para desenvolvimento sem PostgreSQL, configure `DATABASE_URL=sqlite:///./monitoramento.db`. Em produção, use a URL do pooler do Supabase em `DATABASE_URL`.

Execute verificações com:

```bash
ruff check .
pytest
```

## Google Sheets

1. Crie uma Service Account no Google Cloud e habilite a Google Sheets API.
2. Compartilhe cada planilha com o e-mail da conta, como **Editor**.
3. Guarde o JSON inteiro em `GOOGLE_SERVICE_ACCOUNT_JSON` ou codifique-o em Base64 e use `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`.
4. Cadastre a empresa em `companies`, incluindo `spreadsheet_id`, nome da aba principal e e-mails responsáveis.

A aba principal deve ter, no mínimo, `NOME COMPLETO`. Os tipos de requisitos são configurados em `requirement_types`, ligando o cabeçalho da planilha a um código interno. A normalização ignora acentos, quebras, hífens e diferenças de caixa. Colunas de automação preexistentes são atualizadas em lote; não são alterados dados de origem. As abas `Historico_Notificacoes` e `Execucoes` são criadas quando ausentes.

## Empresas e requisitos

Rode a seed para criar `EMPRESA_A`, `EMPRESA_B` e `EMPRESA_C` fictícias, regras de 30/21/14/7/3/1/hoje/vencido e alguns requisitos base. Substitua apenas os IDs de planilha e destinatários no banco; não versione dados reais.

Para nova empresa, insira uma linha em `companies` e compartilhe a nova planilha com a mesma Service Account. Para novo treinamento, insira um `requirement_type` com `code`, `name`, `category` e `spreadsheet_header`.

## API

Todas as rotas administrativas exigem `X-API-Key: <MANUAL_RUN_API_KEY>`.

| Método | Rota | Função |
|---|---|---|
| GET | `/health` | Health check do serviço e banco |
| POST | `/api/v1/executions/run` | Processa todas as empresas ativas |
| POST | `/api/v1/companies/{id}/executions/run` | Processa uma empresa |
| GET | `/api/v1/executions/latest` | Última execução |
| GET | `/api/v1/executions/{id}` | Detalhe de execução |
| GET | `/api/v1/companies` | Empresas |
| GET | `/api/v1/companies/{id}/expirations?days=10` | Vencimentos |
| GET | `/api/v1/companies/{id}/notifications` | Notificações |
| POST | `/api/v1/notifications/{id}/retry` | Libera retry de evento falho |

Em produção, `/docs` e `/openapi.json` ficam desabilitados. Erros de validação retornam Problem Details sem stack trace.

## Painel web (Vercel)

O painel web é mantido em um repositório separado e hospedado na Vercel. Ele consulta a API, permite executar o lote, visualizar empresas, vencimentos e notificações, e possui uma revisão local de arquivos CSV com exportação de uma versão atualizada.

Após publicar o painel e receber sua URL, configure no Render:

```text
CORS_ALLOWED_ORIGINS=https://seu-painel.vercel.app
```

No primeiro acesso, o administrador informa a URL do Render e a `MANUAL_RUN_API_KEY`; esses dados ficam apenas no armazenamento local daquele navegador, nunca no código publicado. A chave continua sendo sensível e deve ser compartilhada somente com administradores autorizados.

## Notificações e segurança

A chave de notificação é SHA-256 de empresa, empregado, requisito, vencimento, regra, canal e destinatário, protegida por índice único. Uma renovação desativa o ciclo anterior, preserva eventos e inicia ciclo novo. CPF/RG não são necessários para a automação e devem permanecer vazios; e-mails são mascarados no histórico de eventos.

Configure SMTP com `MAIL_*`. O sistema envia aos responsáveis da empresa, nunca ao empregado enquanto `NOTIFY_EMPLOYEE=false`.


### E-mail em lote

Configure `MAIL_*` no Render. Os responsáveis cadastrados para cada empresa recebem um e-mail consolidado por execução, sem expor seus endereços entre si. Para também avisar cada colaborador pelo e-mail importado, use `NOTIFY_EMPLOYEE=true`; nessa modalidade, cada pessoa recebe somente os próprios itens.

### E-mail no Render Free

Serviços gratuitos do Render não permitem conexões de saída para portas SMTP. Para o MVP, use a API HTTPS do Brevo:

```env
MAIL_ENABLED=true
MAIL_PROVIDER=brevo
BREVO_API_KEY=sua-chave-da-api-brevo
MAIL_FROM=remetente-verificado@dominio.com
NOTIFY_EMPLOYEE=true
```

Cadastre e valide o remetente no Brevo antes do primeiro envio. O plano gratuito possui 300 envios diários: https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan

### Resumo no Telegram

Crie um bot com o `@BotFather`, adicione-o ao grupo de gestão e configure no Render:

```text
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=<token-do-bot>
TELEGRAM_CHAT_ID=<id-do-grupo>
```

No envio da planilha, informe o campo opcional **Grupo Telegram** para vincular aquele grupo exclusivamente à empresa. O resumo mostra a situação da execução, colaboradores analisados, vencimentos de hoje, itens vencidos, e-mails efetivamente enviados e falhas.

`TELEGRAM_CHAT_ID` é somente um grupo padrão, útil quando todas as empresas do painel pertencem aos mesmos gestores. Para clientes diferentes, deixe essa variável vazia e informe o grupo de cada empresa na importação. O bot não recebe nem armazena credenciais do e-mail.

## Docker e Render

```bash
docker build -t monitoramento-vencimentos .
docker run --env-file .env -p 10000:10000 monitoramento-vencimentos
```

No Render, conecte o repositório, informe as variáveis do `.env.example` no painel e mantenha `APP_ENV=production`. Rode `alembic upgrade head` no processo de release ou manualmente uma vez antes do primeiro deploy. Programe cron-job.org ou um Render Cron Job às 06:00 em `America/Fortaleza` chamando `POST /api/v1/executions/run` com `X-API-Key`.

## Limitações atuais

O processamento HTTP é síncrono para manter o resultado JSON imediatamente disponível; para lotes grandes, mova a chamada para um Render Cron Job/worker. As colunas automáticas precisam existir na aba principal para serem atualizadas (a criação segura dessas colunas deve ser aprovada com o layout de cada empresa). Os testes usam mocks; configure credenciais reais apenas no ambiente de deploy.
