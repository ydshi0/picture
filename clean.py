import os
import re
import glob
import subprocess

# ================= 配置区域 =================
BLOG_DIR = "/Users/syd/blog/source/_posts"
IMG_REPO_DIR = "./blog"
# 保留的 commit 数量
KEEP_COMMITS = 3
# 图片链接匹配正则 (匹配 jsdelivr cdn 格式，不限后缀)
IMG_PATTERN = re.compile(r'https://cdn\.jsdelivr\.net/gh/ydshi0/picture/blog/([^")\s]+)')
# ===========================================


def get_used_images(blog_dir):
    """递归扫描所有子文件夹下的 md 文件，提取被引用的图片文件名"""
    used_images = set()
    md_files = glob.glob(os.path.join(blog_dir, "**", "*.md"), recursive=True)

    for md_file in md_files:
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
                matches = IMG_PATTERN.findall(content)
                used_images.update(matches)
        except Exception as e:
            print(f"[警告] 读取文件失败 {md_file}: {e}")

    print(f"[信息] 共扫描 {len(md_files)} 个 Markdown 文件")
    print(f"[信息] 发现 {len(used_images)} 个被引用的图片:")

    return used_images


def clean_unused_images(img_repo_dir, used_images):
    """对比图片仓库，删除未被引用的文件"""
    if not os.path.exists(img_repo_dir):
        print(f"[错误] 图片仓库目录不存在: {img_repo_dir}")
        return 0

    all_files = [
        f for f in os.listdir(img_repo_dir)
        if os.path.isfile(os.path.join(img_repo_dir, f)) and not f.startswith('.')
    ]
    unused_files = [f for f in all_files if f not in used_images]

    print(f"\n[信息] 图片仓库共有 {len(all_files)} 个文件")
    print(f"[信息] 其中 {len(unused_files)} 个未被引用，将被删除:")

    for f in sorted(unused_files):
        file_path = os.path.join(img_repo_dir, f)
        print(f"  ❌ 删除: {f}")
        os.remove(file_path)

    print(f"\n[完成] 成功清理 {len(unused_files)} 个过期文件")
    return len(unused_files)


def trim_git_history(repo_dir, keep=3):
    """裁剪 Git 仓库历史，只保留最近 keep 个 commit"""
    git_dir = os.path.join(repo_dir, ".git")
    if not os.path.isdir(git_dir):
        print(f"\n[跳过] {repo_dir} 不是 Git 仓库，跳过历史裁剪")
        return

    # 检查当前 commit 总数
    result = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=repo_dir, capture_output=True, text=True
    )
    total_commits = int(result.stdout.strip()) if result.returncode == 0 else 0

    if total_commits <= keep:
        print(f"\n[信息] 当前仅有 {total_commits} 个 commit，无需裁剪（目标保留 {keep} 个）")
        return

    print(f"\n[信息] 当前有 {total_commits} 个 commit，将裁剪为保留最近 {keep} 个...")

    # 获取第 keep 个 commit 的 hash（从 HEAD 往回数）
    base_result = subprocess.run(
        ["git", "rev-parse", f"HEAD~{keep - 1}"],
        cwd=repo_dir, capture_output=True, text=True
    )
    if base_result.returncode != 0:
        print(f"[错误] 无法获取基准 commit: {base_result.stderr.strip()}")
        return
    base_commit = base_result.stdout.strip()

    # 记录当前分支名
    branch_result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_dir, capture_output=True, text=True
    )
    current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "main"

    # 创建临时孤儿分支，以 base_commit 为根
    cmds = [
        ["git", "checkout", "--orphan", "_trim_temp"],
        ["git", "reset", "--soft", base_commit],
        ["git", "commit", "-m", f"Trim history: keep last {keep} commits"],
        ["git", "branch", "-D", current_branch],
        ["git", "branch", "-m", current_branch],
        ["git", "reflog", "expire", "--expire=now", "--all"],
        ["git", "gc", "--prune=now", "--aggressive"],
        # 👇 新增：自动恢复远程追踪关系
        ["git", "branch", "--set-upstream-to", f"origin/{current_branch}", current_branch],
        ["git", "reflog", "expire", "--expire=now", "--all"],
        ["git", "gc", "--prune=now", "--aggressive"],
    ]

    for cmd in cmds:
        r = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[错误] 命令执行失败: {' '.join(cmd)}")
            print(f"       {r.stderr.strip()}")
            # 尝试切回原分支避免停留在临时分支
            subprocess.run(["git", "checkout", current_branch], cwd=repo_dir, capture_output=True)
            return

    print(f"[完成] Git 历史已裁剪，仅保留最近 {keep} 个 commit")


if __name__ == "__main__":
    print("=" * 50)
    print("       博客图片仓库清理工具")
    print("=" * 50)

    used = get_used_images(BLOG_DIR)
    deleted_count = clean_unused_images(IMG_REPO_DIR, used)

    # 直接使用当前目录作为 Git 仓库路径
    trim_git_history(".", keep=KEEP_COMMITS)