#!/bin/bash
#=============================================================================
# 哆啦A梦百宝箱 - 同步脚本
# 将 full 分支的核心代码改动同步到 main，供推送 GitHub 使用
#
# 规则：
#   主体程序 commit → 同步到 main
#   本地专用 commit  → 不推 GitHub
#   混合 commit      → 需手动拆分
#
# 用法：
#   ./bin/sync-to-main.sh           # 交互模式
#   ./bin/sync-to-main.sh --dry-run # 预览
#   ./bin/sync-to-main.sh --force   # 跳过未提交改动检查
#=============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

#----------------------------------------------------------------------------
# 文件分类：core / local / other
#----------------------------------------------------------------------------
_is_core='\.gitignore|main\.py|requirements\.txt|start_gui\.sh|config/|core/|runner/|styles/|utils/|widgets/'

classify_file() {
    local f="$1"
    # 1. README.md → 主体
    [[ "$f" == "README.md" ]] && { echo "core";  return; }
    # 2. scripts/ → 本地
    [[ "$f" == scripts/* ]]   && { echo "local"; return; }
    # 3. param_cache.json → 本地
    [[ "$f" == "param_cache.json" ]] && { echo "local"; return; }
    # 4. 其他 .md 文件 → 本地
    [[ "$f" == *.md ]]        && { echo "local"; return; }
    # 5. 主体程序核心路径 → 主体
    [[ "$f" =~ $_is_core ]]  && { echo "core";  return; }
    # 6. docs/ → 主体
    [[ "$f" == docs/* ]]     && { echo "core";  return; }
    # 7. 其他 → 其他
    echo "other"
}

#----------------------------------------------------------------------------
# 参数解析
#----------------------------------------------------------------------------
DRY_RUN=false; FORCE=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --force)   FORCE=true  ;;
        -h|--help)
            echo "用法: $0 [--dry-run] [--force]"
            exit 0 ;;
        *) echo "未知参数: $arg"; exit 1 ;;
    esac
done

#----------------------------------------------------------------------------
# 工具函数
#----------------------------------------------------------------------------
log_info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[ OK ]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

#----------------------------------------------------------------------------
# 主流程
#----------------------------------------------------------------------------
echo ""
log_info "=== 哆啦A梦百宝箱 同步工具 ==="
echo ""

# 检查分支
current=$(git branch --show-current)
if [[ "$current" != "full" ]]; then
    log_error "当前不在 full 分支（当前: $current）"
    exit 1
fi
log_ok "当前分支: full"

# 检查未提交改动
changes=$(git status --porcelain | awk '$1~/^[AM]$/ {print $2}' || true)
if [[ -n "$changes" ]]; then
    log_warn "存在未提交的改动："
    echo "$changes" | while IFS= read -r f; do
        cls=$(classify_file "$f")
        tag="?"
        [[ "$cls" == "core" ]]  && tag="${GREEN}主体${NC}"
        [[ "$cls" == "local" ]] && tag="${YELLOW}本地${NC}"
        echo -e "  $tag  $f"
    done
    echo ""
    [[ "$FORCE" == "false" ]] && { log_error "请先 commit 或 stash 改动"; exit 1; }
fi

# 检查 main 上游
if git rev-parse --verify main@{u} >/dev/null 2>&1; then
    ahead=$(git rev-list --count main..full 2>/dev/null || echo "?")
    behind=$(git rev-list --count full..main 2>/dev/null || echo "?")
    log_info "main vs full: ahead=$ahead behind=$behind"
else
    log_info "main 尚未设置上游（首次同步）"
fi

echo ""
log_info "=== 分析最近 commit ==="
NUM_COMMITS=${NUM_COMMITS:-5}
log_info "检查最近 $NUM_COMMITS 个 commit..."

# 用临时文件代替 bash 数组，避免 hash key 解析问题
tmp_core=$(mktemp)
tmp_local=$(mktemp)
tmp_mixed=$(mktemp)

cleanup() { rm -f "$tmp_core" "$tmp_local" "$tmp_mixed"; }
trap cleanup EXIT

git log --oneline -n "$NUM_COMMITS" | while IFS= read -r line; do
    hash=${line%% *}
    msg=${line#* }
    files=$(git diff-tree --no-commit-id --name-only -r "$hash" 2>/dev/null || true)

    has_core=false; has_local=false; is_pure=true
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        cls=$(classify_file "$f")
        case "$cls" in
            core)  has_core=true ;;
            local) has_local=true ;;
            other) is_pure=false ;;
        esac
    done <<< "$files"

    # pure = 全部是 core 或 全部是 local（无 unknown 文件）
    if [ "$has_core" = "true" ] && [ "$has_local" != "true" ] && [ "$is_pure" = "true" ]; then
        # 全 core → 主体程序
        printf 'C\t%s\t%s\n' "$hash" "$msg" >> "$tmp_core"
    elif [ "$has_local" = "true" ] && [ "$has_core" != "true" ]; then
        # 全 local（无 core）→ 本地专用
        printf 'L\t%s\t%s\n' "$hash" "$msg" >> "$tmp_local"
    else
        # 包含 core+local 混合，或含 unknown 文件 → 需手动处理
        printf 'M\t%s\t%s\n' "$hash" "$msg" >> "$tmp_mixed"
    fi
done

#----------------------------------------------------------------------------
# 预览
#----------------------------------------------------------------------------
echo ""
log_info "=== commit 分类预览 ==="

core_count=$(wc -l < "$tmp_core")
local_count=$(wc -l < "$tmp_local")
mixed_count=$(wc -l < "$tmp_mixed")

echo -e "${GREEN}主体程序 commit（将同步到 main）：${NC}"
[[ "$core_count" -eq 0 ]] && echo "  （无）" || sed 's/^/  → /' "$tmp_core" | sed 's/→ /\→ /'

echo ""
echo -e "${YELLOW}本地专用 commit（不推 GitHub）：${NC}"
[[ "$local_count" -eq 0 ]] && echo "  （无）" || sed 's/^/  ⌀ /' "$tmp_local"

if [[ "$mixed_count" -gt 0 ]]; then
    echo ""
    echo -e "${RED}混合 commit（需手动处理）：${NC}"
    while IFS=$'\t' read -r _ hash msg; do
        echo -e "  ${RED}!${NC}  $hash  $msg"
        git diff-tree --no-commit-id --name-only -r "$hash" 2>/dev/null | \
            while IFS= read -r f; do
                echo -e "      $f"
            done
    done < "$tmp_mixed"
fi
echo ""

#----------------------------------------------------------------------------
# 执行
#----------------------------------------------------------------------------
if [[ "$core_count" -eq 0 ]]; then
    [[ "$DRY_RUN" == "true" ]] && log_warn "[DRY-RUN] 预览模式，无实际操作"
    log_ok "没有需要同步到 main 的 commit"
    exit 0
fi

if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "[DRY-RUN] 预览模式，不执行实际操作"
    exit 0
fi

log_info "=== 开始同步到 main ==="
git checkout main
log_ok "切换到 main"

# 按时间顺序 cherry-pick core commits
while IFS=$'\t' read -r _ hash msg; do
    ct=$(git log --format='%ct' "$hash" -n1)
    echo "$ct $hash $msg"
done < "$tmp_core" | sort -n | while read -r ct hash msg; do
    log_info "Cherry-pick: $hash  $msg"
    if git cherry-pick "$hash" --no-commit 2>&1; then
        git commit --no-verify -m "$msg"
        log_ok "  → main commit 已创建"
    else
        log_error "  → 冲突，请手动解决："
        echo "    git add . && git commit --no-verify -m \"$msg\""
        echo "    然后运行：git cherry-pick --continue"
        exit 1
    fi
done

echo ""
log_ok "=== 同步完成 ==="
echo ""
echo "请检查 main 分支："
echo "  git log main --oneline -n 10"
echo ""
echo "确认无误后推送 GitHub："
echo "  git push origin main:master"
echo ""
echo "然后切回 full："
echo "  git checkout full"
echo ""
