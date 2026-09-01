# vendor/

第三方依赖目录,通过 git submodule 拉取。

## prc-law-data (默认 submodule)

```bash
git submodule add https://github.com/your-org/prc-law-data.git vendor/prc-law-data
git submodule update --init --recursive
```

更新:
```bash
git submodule update --remote vendor/prc-law-data
```

## 本地开发 (无需 git 凭证)

```bash
ln -sfn ../../prc-law-data vendor/prc-law-data
```

(指向同级 prc-law-data 仓库)

详见:
- [../prc-law-data/README.md](../prc-law-data/README.md)
- [../_foundation/cn-fallback-source/SKILL.md](../_foundation/cn-fallback-source/SKILL.md)