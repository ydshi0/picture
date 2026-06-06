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


def run_git(cmd, cwd):
    """执行 git 命令并返回结果"""
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"命令失败: {' '.join(cmd)}\n{r.stderr.strip()}")
    return r.stdout.strip()


def trim_git_history(repo_dir, keep=3):
    """裁剪 Git 仓库历史，只保留最近 keep 个 commit（各自独立保留）"""
    git_dir = os.path.join(repo_dir, ".git")
    if not os.path.isdir(git_dir):
        print(f"\n[跳过] {repo_dir} 不是 Git 仓库，跳过历史裁剪")
        return

    try:
        total_commits = int(run_git(["git", "rev-list", "--count", "HEAD"], repo_dir))
    except RuntimeError:
        print("[错误] 无法获取 commit 数量")
        return

    if total_commits <= keep:
        print(f"\n[信息] 当前仅有 {total_commits} 个 commit，无需裁剪（目标保留 {keep} 个）")
        return

    print(f"\n[信息] 当前有 {total_commits} 个 commit，将裁剪为保留最近 {keep} 个...")

    try:
        current_branch = run_git(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_dir)
    except RuntimeError:
        current_branch = "main"

    # 获取要保留的 commit 列表（从旧到新）
    try:
        log_output = run_git(
            ["git", "log", f"-{keep}", "--reverse", "--format=%H"],
            repo_dir
        )
        commits = log_output.strip().split('\n')
    except RuntimeError as e:
        print(f"[错误] 无法获取 commit 列表: {e}")
        return

    if len(commits) < keep:
        print(f"[错误] 获取到的 commit 数量不足: {len(commits)}")
        return

    oldest_commit = commits[0]
    remaining_commits = commits[1:]

    try:
        # 1. 以最旧的那个 commit 的 tree 创建孤儿分支作为新的根 commit
        run_git(["git", "checkout", "--orphan", "_trim_temp"], repo_dir)

        #清理工作区：删除所有未跟踪文件和目录，避免 cherry-pick 冲突                                                                                       
        run_git(["git", "clean", "-fd"], repo_dir)                                                                                                          
        run_git(["git", "reset", "--hard"], repo_dir)                               

        # 重置 index 到最旧 commit 的状态
        tree_hash = run_git(["git", "rev-parse", f"{oldest_commit}^{{tree}}"], repo_dir)
        run_git(["git", "read-tree", tree_hash], repo_dir)
        run_git(["git", "checkout-index", "-a", "-f"], repo_dir)

        # 获取原 commit 的信息来保留 commit message
        orig_msg = run_git(["git", "log", "-1", "--format=%B", oldest_commit], repo_dir)
        os.environ["GIT_COMMITTER_DATE"] = run_git(
            ["git", "log", "-1", "--format=%cI", oldest_commit], repo_dir
        )
        os.environ["GIT_AUTHOR_DATE"] = run_git(
            ["git", "log", "-1", "--format=%aI", oldest_commit], repo_dir
        )
        run_git(["git", "commit", "-m", orig_msg], repo_dir)

        # 2. 依次 cherry-pick 后续的 commit
        for commit_hash in remaining_commits:
            run_git(["git", "cherry-pick", commit_hash], repo_dir)

        # 3. 替换原分支
        run_git(["git", "branch", "-D", current_branch], repo_dir)
        run_git(["git", "branch", "-m", current_branch], repo_dir)

        # 4. 恢复远程追踪关系
        subprocess.run(
            ["git", "branch", "--set-upstream-to", f"origin/{current_branch}", current_branch],
            cwd=repo_dir, capture_output=True, text=True
        )

        # 5. 清理
        run_git(["git", "reflog", "expire", "--expire=now", "--all"], repo_dir)
        run_git(["git", "gc", "--prune=now", "--aggressive"], repo_dir)

        print(f"[完成] Git 历史已裁剪，保留了最近 {keep} 个独立 commit")

    except RuntimeError as e:
        print(f"[错误] 裁剪过程中出错: {e}")
        subprocess.run(["git", "checkout", current_branch], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "branch", "-D", "_trim_temp"], cwd=repo_dir, capture_output=True)
    finally:
        os.environ.pop("GIT_COMMITTER_DATE", None)
        os.environ.pop("GIT_AUTHOR_DATE", None)


if __name__ == "__main__":
    print("=" * 50)
    print("       博客图片仓库清理工具")
    print("=" * 50)

    used = get_used_images(BLOG_DIR)
    deleted_count = clean_unused_images(IMG_REPO_DIR, used)

    # 直接使用当前目录作为 Git 仓库路径
    trim_git_history(".", keep=KEEP_COMMITS)
