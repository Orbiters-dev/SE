---
type: moc
domain: infra
agents: [data-keeper, communicator]
status: active
created: 2026-04-06
updated: 2026-04-06
tags: [infra, ec2, datakeeper, lightrag]
---

# MOC_인프라

## 에이전트
- **data-keeper** — 통합 데이터 수집 (7 channels)
- **communicator** — 12h 상태 이메일 (PST 0:00 / 12:00 자동 실행)

## EC2 SSH

```bash
# Key push (60s validity)
aws ec2-instance-connect send-ssh-public-key \
  --instance-id i-00195d735d022f057 --instance-os-user ubuntu \
  --ssh-public-key "file://C:/Users/user/.ssh/orbiters_ec2.pub" \
  --region ap-northeast-2

# SSH exec
/c/Windows/System32/OpenSSH/ssh.exe -i "C:/Users/user/.ssh/orbiters_ec2" \
  -o ConnectTimeout=15 -o StrictHostKeyChecking=no \
  ubuntu@13.124.157.191 "CMD"
```

- Django: `/home/ubuntu/export_calculator/`
- PG: `172.31.13.240:5432`, DB=`export_calculator_db`, User=`es_db_user`
- Gunicorn: daemon mode, port 8000
- Django URL prefix: `/api/onzenna/`

## DataKeeper
- **Channels:** Shopify, Amazon Ads (×3), Amazon Sales (×3), Meta, Google, GA4, Klaviyo
- **Grosmimi:** shared client (`03dbca9c`) + own refresh token
- **GA4:** Property `397533207`, OAuth client `99095230973`
- **GitHub Actions:** `data_keeper.yml` 2x daily, `communicator.yml` 2x daily
- **Shared export:** `Shared/datakeeper/latest/` (7 channels)
- **Known issue:** Amazon Ads campaign list 415 (non-blocking)

## LightRAG
```bash
python tools/rag_query.py "query" --mode hybrid
python tools/rag_index.py
bash lightrag/start_server.sh  # localhost:9621
```

## Projects
- [[project_lightrag]]
- [[project_docuseal]]
