#!/bin/bash
# Скрипт для сброса пароля пользователя через Supabase Admin API

USER_EMAIL="${1:-test@numex.app}"
NEW_PASSWORD="${2:-Test123456}"

SERVICE_ROLE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyAgCiAgICAicm9sZSI6ICJzZXJ2aWNlX3JvbGUiLAogICAgImlzcyI6ICJzdXBhYmFzZS1kZW1vIiwKICAgICJpYXQiOiAxNjQxNzY5MjAwLAogICAgImV4cCI6IDE3OTk1MzU2MDAKfQ.DaYlNEoUrrEn2Ig7tqibS-PHK5vgusbcbo7X36XVt4Q"

echo "Получаем ID пользователя $USER_EMAIL..."
USER_ID=$(docker exec -i supabase-db psql -U postgres -t -c "SELECT id FROM auth.users WHERE email = '$USER_EMAIL';" | tr -d ' ')

if [ -z "$USER_ID" ]; then
  echo "✗ Пользователь не найден!"
  exit 1
fi

echo "✓ User ID: $USER_ID"
echo "Обновляем пароль на: $NEW_PASSWORD"

curl -s -X PUT "http://localhost:8000/auth/v1/admin/users/$USER_ID" \
  -H "apikey: $SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"password\": \"$NEW_PASSWORD\"}" | python3 -m json.tool 2>&1 | head -10

echo ""
echo "Проверяем логин..."
curl -s -X POST "http://localhost:8000/auth/v1/token?grant_type=password" \
  -H "apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyAgCiAgICAicm9sZSI6ICJhbm9uIiwKICAgICJpc3MiOiAic3VwYWJhc2UtZGVtbyIsCiAgICAiaWF0IjogMTY0MTc2OTIwMCwKICAgICJleHAiOiAxNzk5NTM1NjAwCn0.dc_X5iR_VP_qT0zsiyj_I_OZ2T9FtRU2BBNWN8Bu4GE" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$USER_EMAIL\",\"password\":\"$NEW_PASSWORD\"}" | python3 -c "import sys,json; t=json.load(sys.stdin); print('✓ Логин успешен! User:', t['user']['email'])" 2>&1 || echo "✗ Логин не прошёл"

echo ""
echo "Готово! Используйте:"
echo "  Email: $USER_EMAIL"
echo "  Пароль: $NEW_PASSWORD"
