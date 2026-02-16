# Ananda - Sistema Completo PRD

## Problem Statement
Sistema de bot espiritual Ananda com dois bots Telegram:
1. **Bot Principal (Ananda)**: Conversas espirituais, meditações, orações
2. **Bot de Pagamentos**: Vendas, assinaturas, doações, admin, moderação

## Architecture
- **Backend**: FastAPI + Python-Telegram-Bot + Motor (MongoDB)
- **Frontend**: React + Tailwind CSS (Dashboard Admin)
- **AI**: Gemini 2.5 Flash via Emergent LLM Key
- **Database**: MongoDB
- **Pagamentos**: Mercado Pago (Checkout Pro, PIX)

## Bot de Pagamentos - Comandos Completos

### Usuário:
- `/start`, `/menu` - Menu inicial
- `/premium`, `/vip` - Assinaturas
- `/meditacao`, `/pacote`, `/oracao` - Produtos
- `/doar [valor]` - Doação
- `/minhascompras`, `/meusaldo` - Conta

### Admin - Gerenciamento:
- `/ban [ID] [motivo]` - Banir
- `/unban [ID]` - Desbanir
- `/mute [ID] [min]` - Silenciar
- `/unmute [ID]` - Remover silêncio
- `/warn [ID] [motivo]` - Advertir
- `/resetwarn [ID]` - Zerar warns
- `/info [ID]` - Info completa

### Admin - Moderação Automática:
- `/antiflood [on/off/config]` - Proteção flood
- `/antipalavroes [on/off]` - Filtro palavrões
- `/autoban [on/off]` - Ban automático

### Admin - Relatórios:
- `/stats` - Estatísticas
- `/vendas` - Vendas recentes
- `/usuarios` - Lista usuários
- `/banidos` - Lista banidos
- `/mutados` - Lista silenciados
- `/logs [qtd]` - Logs moderação
- `/admin` - Ajuda completa

### Admin - Comunicação:
- `/broadcast [msg]` - Enviar para todos
- `/dm [ID] [msg]` - Mensagem direta

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
- [x] AntiFlood e AntiPalavrões
- [x] Ban/Unban/Mute/Unmute
- [x] Sistema de advertências
- [x] Logs de moderação
- [x] Broadcast e DM
