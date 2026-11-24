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

compose() { docker compose "$@"; }

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

wait_for_api() {
    info "Жду, пока API запустится…"
    for _ in $(seq 1 60); do
        if curl -fs "$API_URL/api/health" >/dev/null 2>&1; then
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

${BOLD}Настройка и данные${RESET}
  setup        Только подготовка: проверить Docker, создать .env, сгенерировать пароль, собрать образы
  password     Показать пароль тестовых аккаунтов
  reset        Стереть базу и создать заново с тестовыми данными (спросит подтверждение)
  help         Эта справка

${BOLD}Примеры${RESET}
  ./run.sh start               ${DIM}# первый запуск — всё настроится само${RESET}
  ./run.sh test -k cart        ${DIM}# только тесты корзины${RESET}
  ./run.sh rebuild test        ${DIM}# пересобрать и сразу прогнать тесты${RESET}
  ./run.sh reset -y            ${DIM}# стереть базу без вопроса${RESET}

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
            locales)        cmd_locales ;;
            db)             cmd_db ;;
            shell)          cmd_shell ;;
            logs)           cmd_logs ${@+"$@"}; return ;;
            test)           cmd_test ${@+"$@"}; return ;;
            migration)      cmd_migration ${@+"$@"}; return ;;
            *)              die "Неизвестная команда «$cmd». Список команд: ./run.sh help" ;;
        esac
    done
}

main "$@"
