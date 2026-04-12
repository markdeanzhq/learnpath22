#!/usr/bin/env bash
set -e

echo "=== LearnPath-KG 初始化脚本 ==="

# 1. 复制环境变量文件
if [ ! -f .env ]; then
  cp .env.example .env
  echo "[OK] .env 已从 .env.example 创建"
else
  echo "[SKIP] .env 已存在"
fi

# 2. 启动服务
echo "[INFO] 启动 Docker 服务..."
docker compose up -d --build

# 3. 等待 API 健康
echo "[INFO] 等待 API 就绪..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health > /dev/null 2>&1; then
    echo "[OK] API 已就绪"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "[ERROR] API 启动超时"
    exit 1
  fi
  sleep 2
done

# 4. 同步 Domain Pack 到 Neo4j
echo "[INFO] 同步知识图谱到 Neo4j..."
curl -sf -X POST http://localhost:8000/api/v1/graph/seed || echo "[WARN] 图谱同步失败（可手动重试）"

echo ""
echo "=== 初始化完成 ==="
echo "前端: http://localhost"
echo "后端 API: http://localhost:8000/api/v1/health"
echo "Neo4j Browser: http://localhost:7474"
echo "Swagger UI: http://localhost:8000/docs"
