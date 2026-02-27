#!/usr/bin/env bash
# Копирует официальный Docker-стак Supabase в текущий каталог (fintech-app/supabase/).
# Запускать из каталога fintech-app/supabase/.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUPABASE_DIR="$(dirname "$SCRIPT_DIR")"
TMP_DIR="${TMPDIR:-/tmp}/supabase-fetch-$$"

trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR"
git clone --depth 1 https://github.com/supabase/supabase "$TMP_DIR/supabase"

cp -rf "$TMP_DIR/supabase/docker/"* "$SUPABASE_DIR/"
if [ -f "$TMP_DIR/supabase/docker/.env.example" ]; then
  if [ ! -f "$SUPABASE_DIR/.env" ]; then
    cp "$TMP_DIR/supabase/docker/.env.example" "$SUPABASE_DIR/.env"
    echo "Создан $SUPABASE_DIR/.env из .env.example. Настройте секреты перед запуском."
  else
    echo "Файл .env уже существует, не перезаписываем."
  fi
fi
echo "Готово. Содержимое supabase/docker скопировано в $SUPABASE_DIR"
