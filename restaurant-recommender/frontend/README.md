# TastyGo Frontend

React + TypeScript 单页应用，驱动 TastyGo 餐厅推荐体验。界面组件最初由 NetEase Tango 设计器导出，并调用 FastAPI `/recommend` 接口获取餐厅推荐。

## 快速开始

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 配置后端地址（默认 http://localhost:8010）
echo "VITE_API_BASE=http://localhost:8010" > .env.local

# 启动开发服务器
npm run dev

# 构建产物
npm run build
```

> **注意**：仓库默认 Node 18。Vite 7 在 Node 18 下会提示 engine 警告，可忽略或升级 Node ≥ 20。

## 目录结构

```
src/
  api/recommend.ts       # Fetch 封装，含类型守卫与错误处理
  components/            # 搜索框、结果卡片、Markdown 视图等原子组件
  pages/Home.tsx         # 主页面（状态管理、视图切换、Skeleton）
  tango/                 # 存放 TastyGo 使用的（来自 Tango 设计器的）组件片段
  types.ts               # 与 FastAPI 契约对齐的 TypeScript 类型
```

## 设计器工作流

1. 打开 `tango` 仓库中的 playground 或自建设计器，导出组件源码。
2. 将导出的组件放入 `src/tango/`，并通过 `export * from './tango/...';` 方式在 `components` 中引用。
3. 调整样式后执行 `npm run lint` / `npm run build` 验证。

更多细节请见 `src/tango/README.md`。

## 环境变量

| 变量名          | 说明                                           | 默认值                |
|----------------|-----------------------------------------------|----------------------|
| `VITE_API_BASE` | 后端 FastAPI 服务地址（需启用 CORS / HTTPS）     | `http://localhost:8010` |
| `VITE_MAPBOX_TOKEN` | Mapbox 地图 Token（如启用）                    | 无                    |

开发阶段可在 `.env.local` 覆盖。生产构建读取 `.env.production`。

## 常见问题

- **跨域 / HTTPS**：后端已允许 `*`。如需 https，可通过 `mkcert` 生成证书并配置 Vite 代理。
- **Geoapify Attribution**：部署时需在界面显著位置展示“powered by Geoapify”。
- **密钥安全**：不要将 Geoapify/Mapbox 密钥写死在前端；通过代理或后端注入。
- **构建失败**：请确认 Node >= 18；若使用 PNPM / Yarn，删除 `package-lock.json` 并重新安装。

## 质量校验

- `npm run lint`：ESLint + TypeScript 检查（如需可添加）
- `npm run build`：确保产物可生成并供部署
- `npm run preview`：本地预览生产构建

## 相关文档

- [FastAPI 后端 README](../backend/README.md)
- [Tango 项目主页](https://github.com/NetEase/tango)（TastyGo UI 组件来源）
