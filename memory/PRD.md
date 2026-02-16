# Ananda - Sistema Completo PRD

## Problem Statement
Sistema de bot espiritual Ananda com dois bots Telegram:
1. **Bot Principal (Ananda)**: Conversas espirituais, meditações, orações
2. **Bot de Pagamentos**: Vendas, assinaturas, doações, admin, moderação

## Architecture
- **Backend**: FastAPI + Python-Telegram-Bot + Motor (MongoDB)
- **Frontend**: React + Tailwind CSS (Dashboard Admin + Dashboard Vendas)
- **AI**: Gemini 2.5 Flash via Emergent LLM Key
- **Database**: MongoDB
- **Pagamentos**: Mercado Pago (Checkout Pro, PIX)

## Dashboard Web

### Abas Disponíveis:
1. **Dashboard** - Visão geral do bot
2. **Vendas** - Dashboard de vendas e receita (NOVO)
3. **Usuários** - Gerenciamento de usuários
4. **Mensagens** - Monitoramento de conversas
5. **Pedidos** - Pedidos de oração
6. **Aprendizados** - IA aprendizados
7. **Broadcast** - Enviar mensagens

### Dashboard de Vendas:
- Cards de métricas (Receita Total, Hoje, Semana, Mês)
- Gráfico de receita dos últimos 7 dias
- Top 5 compradores
- Vendas por produto
- Lista de transações com filtros

## Bot de Pagamentos - Comandos

### Usuário:
- `/start`, `/menu`, `/premium`, `/vip`
- `/meditacao`, `/pacote`, `/oracao`, `/doar [valor]`
- `/minhascompras`, `/meusaldo`

### Admin - Moderação:
- `/ban`, `/unban`, `/mute`, `/unmute`
- `/warn`, `/resetwarn`, `/info`
- `/antiflood`, `/antipalavroes`, `/autoban`
- `/banidos`, `/mutados`, `/logs`
- `/broadcast`, `/dm`, `/admin`

## Environment Variables
```
MONGO_URL=mongodb://localhost:27017
DB_NAME=test_database
TG_TOKEN=<token_bot_ananda>
ADMIN_ID=<seu_telegram_id>
EMERGENT_LLM_KEY=<key>
MP_ACCESS_TOKEN=APP_USR-xxx
MP_PUBLIC_KEY=APP_USR-xxx
PAYMENT_BOT_TOKEN=8273296855:AAEFVbo3ADqgfhfgSvVaZ5OCyQfbaLRyofE
REACT_APP_BACKEND_URL=https://seu-dominio.com
```

## What's Been Implemented (Feb 2026)
- [x] Integração Mercado Pago
- [x] Bot de Pagamentos separado
- [x] Sistema de moderação completo
- [x] Dashboard de Vendas no frontend
- [x] Gráficos e métricas de receita
- [x] Lista de transações com filtros
- [x] Top compradores
- [x] Vendas por produto
