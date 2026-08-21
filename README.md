# Worklog 轻量工作日志

面向个人和小团队的轻量工时记录工具，针对 2核2G、同时运行其他服务的 Linux/ECS 环境设计。

## 保留的功能

- 多人员切换，研发/测试活动模板
- 按日期填报、修改和删除工作记录
- 月历工时、当日/本周/本月汇总、分类统计
- 历史记录筛选
- CSV 导入导出
- SQLite 原生一致性备份（保留最近 10 份）
- 可选共享访问密码、CSRF 防护、健康检查

## 资源设计

- Flask + 原生 SQLite + 原生 CSV，无 pandas、Streamlit、openpyxl
- Gunicorn 默认 1 worker / 2 threads
- systemd：`MemoryHigh=220M`、`MemoryMax=320M`、最多使用 1 核
- SQLite WAL 模式，适合低并发小团队使用

## 本地启动

要求 Python 3.9+：

```bash
./run.sh
```

默认只监听 `127.0.0.1:8501`。后台运行：

```bash
./run.sh bg
./stop.sh
```

可选环境变量：

```bash
export WORKLOG_PASSWORD='访问密码'
export WORKLOG_SECRET_KEY='固定随机密钥'
export WORKLOG_ADDRESS='127.0.0.1'
export WORKLOG_PORT='8501'
```

浏览器访问 <http://127.0.0.1:8501>，健康检查为 `/healthz`。

## 部署到阿里云 ECS

建议让应用仅监听本机地址，通过服务器已有的 Nginx/Caddy 提供 HTTPS：

```bash
WORKLOG_HOST=服务器IP \
WORKLOG_USER=root \
WORKLOG_PASSWORD='访问密码' \
./scripts/deploy_ecs.sh
```

脚本会部署到 `/opt/worklog`，创建低权限用户 `worklog`，安装 systemd 服务并保留服务器已有数据库。

Nginx 反向代理示例：

```nginx
location / {
    proxy_pass http://127.0.0.1:8501;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

如果必须直接通过安全组访问，可在部署时设置 `WORKLOG_ADDRESS=0.0.0.0`，但应限制安全组来源 IP。

## 数据与维护

- 主数据库：`data/worklog.db`
- 备份：`reports/worklog_backup_*.db`
- 查看日志：`journalctl -u worklog -f`
- 重启服务：`systemctl restart worklog`
- 测试：`python -m unittest discover -s tests -v`

从旧 Streamlit 版本启动时会自动迁移并保留已有人员和工时数据。
