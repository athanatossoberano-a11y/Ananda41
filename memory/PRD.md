# Ananda - Sistema Completo PRD

## Problem Statement
Sistema de bot espiritual Ananda com dois bots Telegram:
1. **Bot Principal (Ananda)**: Conversas espirituais, meditações, orações
2. **Bot de Pagamentos**: Vendas, assinaturas, doações, admin

## Architecture
- **Backend**: FastAPI + Python-Telegram-Bot + Motor (MongoDB)
- **Frontend**: React + Tailwind CSS (Dashboard Admin)
- **AI**: Gemini 2.5 Flash via Emergent LLM Key
- **Database**: MongoDB
- **Pagamentos**: Mercado Pago (Checkout Pro, PIX)

## Modelos de Monetização

### Assinaturas Mensais
| Plano | Preço | Benefícios |
|-------|-------|------------|
| Gratuito | R$ 0 | 10 conversas/dia |
| Premium | R$ 19,90/mês | Conversas ilimitadas, meditações, orações |
| VIP | R$ 39,90/mês | Tudo Premium + conteúdo exclusivo |

### Compras Avulsas
| Produto | Preço | Descrição |
|---------|-------|-----------|
| Meditação | R$ 4,90 | 1 meditação guiada |
| Pacote 10 | R$ 29,90 | 10 meditações (economia R$ 19,10) |
| Oração | R$ 2,90 | 1 oração personalizada |

### Doação Voluntária
- Valor livre (mínimo R$ 1,00)

## Bots Telegram

### Bot Principal (Ananda) - TG_TOKEN
**Comandos Usuário:**
- `/start`, `/help`, `/meditar`, `/orar`, `/versiculo`
- `/pedido`, `/compartilhar`, `/meunome`
- `/assinar`, `/meuplano`, `/premium`, `/vip`

**Comandos Admin:**
- `/stats`, `/users`, `/online`, `/check`, `/msg`
- `/historico`, `/ban`, `/unban`, `/resetwarn`
- `/broadcast`, `/pedidos`, `/enviarversiculo`

### Bot de Pagamentos - PAYMENT_BOT_TOKEN
**Comandos Usuário:**
- `/start`, `/menu` - Menu inicial
- `/premium`, `/vip` - Assinaturas
- `/meditacao`, `/pacote`, `/oracao` - Produtos
- `/doar [valor]` - Doação
- `/minhascompras`, `/meusaldo` - Conta

**Comandos Admin:**
- `/stats` - Estatísticas e receita
- `/vendas` - Relatório de vendas
- `/usuarios` - Lista de usuários

## API Endpoints

### Mercado Pago
- `GET /api/mercadopago/public-key`
- `GET /api/mercadopago/plans`
- `GET /api/mercadopago/products`
- `POST /api/mercadopago/checkout`
- `POST /api/mercadopago/pix`
- `GET /api/mercadopago/payment/{id}`
- `POST /api/mercadopago/webhook`
- `GET /api/mercadopago/payments`

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
- [x] Integração Mercado Pago completa
- [x] Bot de Pagamentos separado
- [x] Assinaturas Premium/VIP
- [x] Produtos avulsos (meditação, oração)
- [x] Doações voluntárias
- [x] Histórico de compras
- [x] Painel admin no bot de pagamentos
- [x] Webhooks para ativação automática

## Backlog

### P0 (Urgente)
- [ ] Configurar TG_TOKEN para bot Ananda
- [ ] Configurar ADMIN_ID

### P1 (Próximo)
- [ ] Sistema de créditos (meditações/orações compradas)
- [ ] Notificação push após pagamento aprovado
- [ ] Painel web de pagamentos

### P2 (Futuro)
- [ ] Cupons de desconto
- [ ] Programa de indicação
- [ ] Relatórios exportáveis
