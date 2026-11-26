#!/usr/bin/env bash
# Technology-Store: one script to set up, run and maintain the project.
#
# Usage: ./run.sh <command> [<command> ...] [-y]
# Run ./run.sh help for the list of commands.
#
# Works with the bash that ships with macOS (3.2), so no bash 4+ features here.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PROJECT="$(basename "$ROOT" | tr '[:upper:]' '[:lower:]')"  # docker compose project name
API_URL="http://localhost:8000"
SEED_EMAILS="admin@store.dev, manager@store.dev, engineer@store.dev, client@store.dev"
ASSUME_YES=0

# ---------- output ----------

if [ -t 1 ]; then
    BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; RESET=$'\033[0m'
else
    BOLD=""; DIM=""; GREEN=""; YELLOW=""; RED=""; RESET=""
fi

info() { printf '%s==>%s %s\n' "$GREEN" "$RESET" "$*"; }
warn() { printf '%s!  %s%s\n' "$YELLOW" "$*" "$RESET" >&2; }
die()  { printf '%sОшибка:%s %s\n' "$RED" "$RESET" "$*" >&2; exit 1; }

# `docker compose exec` needs -T when there is no terminal (CI, pipes)
if [ -t 0 ] && [ -t 1 ]; then TTY_FLAG=""; else TTY_FLAG="-T"; fi

# On a server (RUN_MODE=server in .env, set by ./run.sh deploy) every command also uses
# docker-compose.prod.yml: only Caddy is open outside, see docs/DEPLOY.md.
server_mode() { [ -f .env ] && grep -qE '^RUN_MODE=server$' .env; }
compose() {
    if server_mode; then
        docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"
    else
        docker compose "$@"
    fi
}

# ---------- helpers ----------

check_docker() {
    command -v docker >/dev/null 2>&1 \
        || die "Docker не установлен. Скачайте Docker Desktop: https://www.docker.com/products/docker-desktop/"
    docker compose version >/dev/null 2>&1 \
        || die "Нужен Docker Compose v2 (команда «docker compose»). Обновите Docker Desktop."

    if ! docker info >/dev/null 2>&1; then
        if [ "$(uname)" = "Darwin" ]; then
            info "Docker не запущен, запускаю Docker Desktop…"
            open -a Docker >/dev/null 2>&1 || die "Не удалось запустить Docker Desktop. Запустите его вручную."
            for _ in $(seq 1 60); do
                docker info >/dev/null 2>&1 && break
                sleep 2
            done
        fi
        docker info >/dev/null 2>&1 || die "Docker не запущен. Запустите Docker Desktop и повторите команду."
    fi
}

env_get() {  # value of a key in .env (empty if missing)
    [ -f .env ] || return 0
    grep -E "^$1=" .env | tail -n 1 | cut -d= -f2- || true
}

env_set() {  # set a key in .env (replace or append)
    if grep -qE "^$1=" .env; then
        awk -v key="$1" -v value="$2" 'BEGIN { FS = "=" } $1 == key { print key "=" value; next } { print }' \
            .env > .env.tmp && mv .env.tmp .env
    else
        printf '\n%s=%s\n' "$1" "$2" >> .env
    fi
}

random_password() {
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' | cut -c1-20
}

db_volume_exists() {
    docker volume inspect "${PROJECT}_pgdata" >/dev/null 2>&1
}

is_running() {
    [ -n "$(compose ps -q --status running backend 2>/dev/null)" ]
}

api_alive() {
    if server_mode; then  # on a server the API port is closed: ask from inside its container
        compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" >/dev/null 2>&1
    else
        curl -fs "$API_URL/api/health" >/dev/null 2>&1
    fi
}

wait_for_api() {
    info "Жду, пока API запустится…"
    for _ in $(seq 1 60); do
        if api_alive; then
            return 0
        fi
        sleep 2
    done
    warn "API не ответил за 2 минуты. Последние строки лога:"
    compose logs --tail=30 backend >&2
    exit 1
}

ensure_running() {
    check_docker
    is_running || cmd_start
}

confirm() {
    [ "$ASSUME_YES" = "1" ] && return 0
    [ -t 0 ] || die "$1 Для подтверждения без вопроса добавьте -y."
    printf '%s [y/N] ' "$1"
    read -r answer
    case "$answer" in y|Y|yes|д|Д|да) return 0 ;; *) info "Отменено."; exit 0 ;; esac
}

ensure_seed_password() {
    # The password is applied only when the database is created, so generate it only then.
    if [ -z "$(env_get SEED_PASSWORD)" ] && ! db_volume_exists; then
        env_set SEED_PASSWORD "$(random_password)"
        info "Сгенерирован пароль тестовых аккаунтов (сохранён в .env, показать: ./run.sh password)"
    fi
}

# ---------- commands ----------

cmd_help() {
    cat <<EOF
${BOLD}Technology-Store${RESET} — управление проектом одной командой.

${BOLD}Использование:${RESET} ./run.sh <команда> [<команда> ...] [-y]

${BOLD}Основное${RESET}
  start        Всё сразу: проверить Docker, настроить, собрать и запустить в фоне
  stop         Остановить проект (данные базы сохраняются)
  restart      Перезапустить
  status       Какие контейнеры запущены
  logs [svc]   Логи в реальном времени (по умолчанию backend; ещё: frontend, db, adminer). Выход: Ctrl+C

${BOLD}Разработка${RESET}
  test [args]  Запустить автотесты (аргументы передаются в pytest: -k bonus, tests/test_auth.py, -x)
  rebuild      Пересобрать образы (после изменения requirements.txt или Dockerfile) и запустить
  migration "описание"
               Создать миграцию после изменения backend/app/models.py
  locales      Проверить, что переводы ru/en совпадают по ключам
  db           Открыть консоль PostgreSQL (psql)
  shell        Открыть терминал внутри контейнера бэкенда
  ide          Подготовить редактор кода (VS Code / Pylance): локальные библиотеки Python
               в backend/.venv, чтобы не было ошибок «Import could not be resolved»
  typecheck    Проверить типы в коде бэкенда (то же, что подсвечивает Pylance)

${BOLD}Настройка и данные${RESET}
  setup        Только подготовка: проверить Docker, создать .env, сгенерировать пароль, собрать образы
  password     Показать пароль тестовых аккаунтов
  reset        Стереть базу и создать заново с тестовыми данными (спросит подтверждение)
  photos       Подключить настоящие фото товаров (resources/photos/web); у кого их нет — заглушка
  models       Пересобрать 3D-модели конфигуратора в Blender (resources/models/builder.glb)
  deploy       Запуск на сервере: пароли и ключи генерируются сами, наружу только 80/443,
               HTTPS, если в .env указан домен (SITE_ADDRESS). Подробнее: docs/DEPLOY.md
  demo         Наполнить базу демо-данными: ещё товары с картинками, новости и события,
               клиенты с заказами, сборки, ремонт, поставки (один раз; заново — reset, потом demo)
  help         Эта справка

${BOLD}Примеры${RESET}
  ./run.sh start               ${DIM}# первый запуск — всё настроится само${RESET}
  ./run.sh test -k cart        ${DIM}# только тесты корзины${RESET}
  ./run.sh rebuild test        ${DIM}# пересобрать и сразу прогнать тесты${RESET}
  ./run.sh reset -y            ${DIM}# стереть базу без вопроса${RESET}
  ./run.sh reset -y demo       ${DIM}# чистая база, сразу с демо-данными${RESET}

Команды можно писать подряд — они выполнятся по очереди.
logs, test и migration забирают все аргументы после себя, поэтому ставьте их последними.

${BOLD}Адреса после запуска${RESET}
  Сайт                http://localhost:5173
  API и документация  $API_URL/docs
  Adminer (база)      http://localhost:8080
EOF
}

cmd_setup() {
    check_docker
    if [ ! -f .env ]; then
        cp .env.example .env
        info "Создан .env из .env.example"
    fi
    ensure_seed_password
    if [ -z "$(env_get SEED_PASSWORD)" ]; then
        warn "SEED_PASSWORD в .env пустой, а база уже создана — пароль был выведен в лог при её создании."
        warn "Посмотреть: ./run.sh password. Взять пароль из .env: ./run.sh reset"
    fi
    info "Собираю образы…"
    compose build
}

cmd_start() {
    check_docker
    if [ ! -f .env ]; then
        cmd_setup
    else
        ensure_seed_password
    fi
    info "Запускаю…"
    compose up -d
    wait_for_api
    if server_mode; then
        print_server_address
        return
    fi
    printf '\n%sГотово!%s\n' "$BOLD" "$RESET"
    printf '  Сайт                http://localhost:5173\n'
    printf '  API и документация  %s/docs\n' "$API_URL"
    printf '  Adminer (база)      http://localhost:8080\n'
    printf '  Тестовые аккаунты   ./run.sh password\n'
    printf '  Остановить          ./run.sh stop\n\n'
}

cmd_stop() {
    check_docker
    info "Останавливаю…"
    compose down
}

cmd_restart() {
    cmd_stop
    cmd_start
}

cmd_status() {
    check_docker
    compose ps
}

cmd_logs() {
    check_docker
    if [ $# -eq 0 ]; then set -- backend; fi
    compose logs -f --tail=100 "$@"
}

cmd_rebuild() {
    check_docker
    [ -f .env ] || cmd_setup
    info "Пересобираю и запускаю…"
    compose up -d --build
    wait_for_api
}

cmd_reset() {
    check_docker
    confirm "Все данные в базе (заказы, пользователи, изменения товаров) будут удалены. Продолжить?"
    info "Удаляю контейнеры и базу…"
    compose down -v
    cmd_start
}

# ---------- server (docs/DEPLOY.md) ----------

is_default_secret() {  # empty, or a value from .env.example that must never be used on a server
    case "$1" in ""|store|dev-secret-change-me) return 0 ;; *) return 1 ;; esac
}

print_server_address() {
    local site
    site="$(env_get SITE_ADDRESS)"
    printf '\n%sСайт запущен в режиме сервера.%s\n' "$BOLD" "$RESET"
    if [ -z "$site" ] || [ "$site" = ":80" ]; then
        printf '  Адрес               http://<IP сервера>\n'
    else
        printf '  Адрес               https://%s\n' "$site"
    fi
    printf '  Пароль аккаунтов    ./run.sh password  (вход: admin@store.dev)\n'
    printf '  Логи                ./run.sh logs  ·  ./run.sh logs caddy\n'
    printf '  Обновить код        git pull && ./run.sh deploy\n\n'
}

cmd_deploy() {
    check_docker
    [ -f .env ] || cp .env.example .env
    # secrets: long random values instead of the examples (the database password only before the database exists)
    if is_default_secret "$(env_get POSTGRES_PASSWORD)"; then
        if db_volume_exists; then
            warn "База уже создана со стандартным паролем — оставляю его. Чтобы сменить: ./run.sh reset -y (данные удалятся)."
        else
            env_set POSTGRES_PASSWORD "$(random_password)$(random_password)"
            info "Сгенерирован пароль базы данных"
        fi
    fi
    if is_default_secret "$(env_get JWT_SECRET)"; then
        env_set JWT_SECRET "$(random_password)$(random_password)$(random_password)"
        info "Сгенерирован JWT_SECRET (ключ подписи входа)"
    fi
    ensure_seed_password
    [ -n "$(env_get SITE_ADDRESS)" ] || env_set SITE_ADDRESS ":80"
    env_set RUN_MODE server
    info "Собираю и запускаю в режиме сервера (наружу открыты только порты 80 и 443)…"
    compose up -d --build --remove-orphans
    wait_for_api
    print_server_address
}

cmd_demo() {
    ensure_running
    info "Добавляю демо-данные…"
    compose exec $TTY_FLAG backend python -m app.demo
}

cmd_photos() {
    ensure_running
    info "Подключаю фото товаров…"
    compose exec $TTY_FLAG backend python -m app.photos
}

cmd_models() {
    # Blender: from PATH, or the usual place on macOS
    local blender
    blender="$(command -v blender || true)"
    [ -n "$blender" ] || [ ! -x /Applications/Blender.app/Contents/MacOS/Blender ] || blender=/Applications/Blender.app/Contents/MacOS/Blender
    [ -n "$blender" ] || die "Нужен Blender 4.2 или новее: https://www.blender.org/download/ (или добавьте blender в PATH)"
    info "Строю 3D-модели конфигуратора в Blender…"
    "$blender" -b -P backend/scripts/make_builder_models.py 2>&1 | grep -E "^made|Error|Traceback" || true
}

cmd_test() {
    ensure_running
    info "Запускаю автотесты…"
    compose exec $TTY_FLAG backend pytest ${@+"$@"}
}

cmd_migration() {
    [ $# -gt 0 ] || die "Укажите описание: ./run.sh migration \"add phone to orders\""
    ensure_running
    compose exec $TTY_FLAG backend alembic revision --autogenerate -m "$*"
    info "Проверьте новый файл в backend/alembic/versions/. Применится при следующем ./run.sh restart"
}

cmd_locales() {
    ensure_running
    compose exec $TTY_FLAG backend python scripts/check_locales.py
}

cmd_db() {
    ensure_running
    compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
}

cmd_shell() {
    ensure_running
    compose exec backend bash
}

cmd_ide() {
    command -v python3 >/dev/null 2>&1 || die "Нужен Python 3.12+ на компьютере: https://www.python.org/downloads/"
    if [ ! -x backend/.venv/bin/python ]; then
        info "Создаю backend/.venv…"
        python3 -m venv backend/.venv
    fi
    info "Ставлю библиотеки бэкенда для редактора…"
    backend/.venv/bin/pip install -q --upgrade pip
    # pillow: for backend/scripts (product photos), they run on the computer, not in the container
    backend/.venv/bin/pip install -q -r backend/requirements.txt basedpyright pillow
    info "Готово. Перезапустите VS Code (или «Python: Restart Language Server») — ошибки импорта пропадут."
    info "Настройки проверки лежат в pyrightconfig.json."
}

cmd_typecheck() {
    [ -x backend/.venv/bin/basedpyright ] || cmd_ide
    backend/.venv/bin/basedpyright
}

cmd_password() {
    local password
    password="$(env_get SEED_PASSWORD)"
    if [ -z "$password" ] && command -v docker >/dev/null 2>&1; then
        # generated by the seed itself: look for it in the backend log
        password="$(compose logs backend 2>/dev/null | grep 'seed:     ' | tail -n 1 | sed 's/.*seed: *//' || true)"
    fi
    [ -n "$password" ] || die "Пароль не найден. Пересоздайте базу: ./run.sh reset (пароль сгенерируется и сохранится в .env)"
    printf 'Аккаунты: %s\n' "$SEED_EMAILS"
    printf 'Пароль:   %s%s%s\n' "$BOLD" "$password" "$RESET"
}

# ---------- main ----------

main() {
    local args=() arg
    for arg in "$@"; do
        case "$arg" in
            -y|--yes) ASSUME_YES=1 ;;
            *) args+=("$arg") ;;
        esac
    done
    if [ ${#args[@]} -eq 0 ]; then
        cmd_help
        return 0
    fi
    set -- "${args[@]}"

    while [ $# -gt 0 ]; do
        local cmd="$1"
        shift
        case "$cmd" in
            help|-h|--help) cmd_help ;;
            setup)          cmd_setup ;;
            start|up)       cmd_start ;;
            stop|down)      cmd_stop ;;
            restart)        cmd_restart ;;
            status|ps)      cmd_status ;;
            rebuild)        cmd_rebuild ;;
            reset)          cmd_reset ;;
            password)       cmd_password ;;
            demo)           cmd_demo ;;
            deploy)         cmd_deploy ;;
            photos)         cmd_photos ;;
            models)         cmd_models ;;
            locales)        cmd_locales ;;
            db)             cmd_db ;;
            shell)          cmd_shell ;;
            ide)            cmd_ide ;;
            typecheck)      cmd_typecheck ;;
            logs)           cmd_logs ${@+"$@"}; return ;;
            test)           cmd_test ${@+"$@"}; return ;;
            migration)      cmd_migration ${@+"$@"}; return ;;
            *)              die "Неизвестная команда «$cmd». Список команд: ./run.sh help" ;;
        esac
    done
}

main "$@"
