#!/bin/bash
source /home/devops/.claude/channels/telegram/.env
CHAT_ID="1312711201"
MSG="⏰ Recordatorio: Han pasado 2 semanas desde el 24/03.

Es momento de decidir si solicitar la revisión de AdSense.

Estado a 24/03:
• PageSpeed móvil: 70
• 56 posts publicados
• Páginas legales completas
• Posts nuevos (Amazon Flex + Convenio) publicados

¿Solicitamos la revisión? 🚀"

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${CHAT_ID}" \
  -d "text=${MSG}" > /dev/null && echo "Reminder sent" || echo "Error sending reminder"
