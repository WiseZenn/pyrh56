# 发布到 PyPI

发行包和命令名为 `pyrh56`，Python 导入名为 `rh56_sdk`。

## GitHub Trusted Publishing

本仓库通过 GitHub Actions 的 OpenID Connect 身份发布，无需保存 PyPI API Token。
PyPI 项目的 Trusted Publisher 需要匹配以下配置：

- Owner：`WiseZenn`
- Repository：`pyrh56`
- Workflow filename：`ci.yaml`，对应 `.github/workflows/ci.yaml`
- Environment：当前未限定环境，工作流也未指定环境

文件名必须一致；`.github/workflows/ci.yml` 是日常 CI，不是登记的发布工作流。
发布作业单独申请 `id-token: write`，只接收前序构建作业已经检查的产物。

## 发布步骤

1. 同步修改 `pyproject.toml` 和 `src/rh56_sdk/__init__.py` 中的版本号，
   更新 `CHANGELOG.md` 的发布日期和变更记录。
2. 提交 PR，确认测试、Ruff、mypy、打包及安全检查通过后合并到 `main`。
3. 从对应的主分支提交创建并推送版本标签，例如：

   ```console
   git fetch origin main
   git tag -a v0.4.0 origin/main -m "Release pyrh56 0.4.0"
   git push origin v0.4.0
   ```

4. 查看 GitHub Actions 中的 **Publish to PyPI**。工作流验证标签与两个版本号一致，
   重新运行检查，构建 wheel/sdist，通过 `twine check --strict` 和安装验证后上传 PyPI。
5. 确认 [PyPI 项目页](https://pypi.org/project/pyrh56/) 的版本和文件，
   在独立环境验证安装后的入口，再为同一标签创建 GitHub Release。

   ```console
   python -m pip install --upgrade "pyrh56==0.4.0"
   pyrh56 --version
   pyrh56 --mock state --json
   python -m rh56_sdk --mock ping --json
   ```

只推送发布标签会触发上传；普通提交和 PR 检查不会上传 PyPI。
已发布的版本保留不动；后续修复使用新版本号和新标签。

参考：[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/)。
