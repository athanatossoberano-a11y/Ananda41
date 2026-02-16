# Ananda - Guia Espiritual Bot PRD

## Problem Statement
Bot Telegram chamado Ananda, guia espiritual e conselheira. Integração com Mercado Pago para pagamentos via Checkout Pro, PIX e Webhooks.

## Architecture
- **Backend**: FastAPI + Python-Telegram-Bot + Motor (MongoDB async)
- **Frontend**: React + Tailwind CSS (Dashboard Admin)
- **AI**: Gemini 2.5 Flash via Emergent LLM Key
- **Database**: MongoDB
- **Pagamentos**: Telegram Stars (XTR) + **Mercado Pago (BRL)**

## Pricing Plans
| Plano | Preço Stars | Preço BRL | Limite Mensagens | Benefícios |
|-------|-------------|-----------|------------------|------------|
| Gratuito | 0 | R$ 0 | 10/dia | Comandos básicos |
| Premium | 200/mês | R$ 19,90/mês | Ilimitado | Meditações, orações, prioridade |
| VIP | 400/mês | R$ 39,90/mês | Ilimitado | Tudo Premium + conteúdo exclusivo |

## What's Been Implemented (Feb 2026)

### Mercado Pago Integration (NEW)
- [x] GET `/api/mercadopago/public-key` - Retorna public key
- [x] GET `/api/mercadopago/plans` - Lista planos com preços BRL
- [x] POST `/api/mercadopago/checkout` - Cria preferência Checkout Pro
- [x] POST `/api/mercadopago/pix` - Cria pagamento PIX com QR Code
- [x] GET `/api/mercadopago/payment/{id}` - Status do pagamento
- [x] POST `/api/mercadopago/webhook` - Recebe notificações MP
- [x] GET `/api/mercadopago/success|failure|pending` - Redirects após pagamento
- [x] GET `/api/mercadopago/payments` - Lista pagamentos MP

### Bot Telegram - Comandos Usuário
- [x] `/start`, `/help`, `/meditar`, `/orar`, `/versiculo`
- [x] `/pedido`, `/compartilhar`, `/meunome`
- [x] `/assinar`, `/meuplano`, `/premium`, `/vip`

### Bot Telegram - Comandos Admin
- [x] `/stats`, `/users`, `/online`, `/check`, `/msg`
- [x] `/historico`, `/ban`, `/unban`, `/resetwarn`
- [x] `/broadcast`, `/pedidos`, `/enviarversiculo`

### Sistema de Pagamentos
- [x] Telegram Stars (XTR)
- [x] Mercado Pago Checkout Pro
- [x] Mercado Pago PIX
- [x] Webhooks para ativação automática
- [x] Limite de 10 msgs/dia para gratuito

## Environment Variables Required
```
# MongoDB
MONGO_URL=mongodb://localhost:27017
DB_NAME=test_database

# Telegram
TG_TOKEN=<seu_token_telegram>
ADMIN_ID=<seu_telegram_id>

# Emergent LLM
EMERGENT_LLM_KEY=<sua_key>

# Mercado Pago
MP_ACCESS_TOKEN=APP_USR-xxx
MP_PUBLIC_KEY=APP_USR-xxx

# URLs
REACT_APP_BACKEND_URL=https://seu-dominio.com
REACT_APP_FRONTEND_URL=https://seu-dominio.com
```

## Prioritized Backlog

### P0 (Urgente)
- [ ] Configurar TG_TOKEN e ADMIN_ID para bot funcionar
- [ ] Configurar webhook URL no painel MP

### P1 (Próximos)
- [ ] Painel de pagamentos no dashboard web
- [ ] Renovação automática de assinatura
- [ ] Notificação de expiração (3 dias antes)

### P2 (Futuro)
- [ ] Cupons de desconto
- [ ] Programa de indicação
- [ ] Trial de 7 dias grátis
