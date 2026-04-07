---
type: architecture
domain: infra
agents: [서버매니저, 앱스터]
status: active
created: 2026-04-07
updated: 2026-04-07
tags: [ssh, sigpipe, exit-141, ec2, deployment]
moc: "[[MOC_인프라]]"
---

# SSH Pipe Exit 141 근본 분석

## TL;DR

Exit 141 = 128 + 13 (SIGPIPE). 로컬 프로세스가 pipe로 데이터를 쓰는 중에 SSH 연결이 끊기면 발생.
**해결책: pipe 절대 쓰지 말고, SCP로 파일 전송 후 EC2에서 실행.**

## 메커니즘

```
로컬: cat file.sql ──[pipe]──> ssh client ──[TCP]──> EC2 sshd ──> psql
                                    │
                              연결 끊김/버퍼 초과
                                    │
                              ← SIGPIPE (signal 13)
                              exit code = 128 + 13 = 141
```

**왜 끊기는가:**
1. EC2 쪽 명령이 먼저 종료 (psql 에러, 디스크 풀 등)
2. SSH TCP 세션 타임아웃 (유휴 시간 초과)
3. Windows OpenSSH 버퍼 크기 한계 (stdout 4KB 기본)
4. EC2 Instance Connect 키 60초 만료 중간에 재접속 시

## 위험도별 현재 SSH 사용처

### CRITICAL (pipe 사용 — 반드시 수정)

| 파일 | 패턴 | 문제 |
|------|------|------|
| `run_migration.yml:29-30` | `cat SQL \| ssh ec2 psql -f -` | SQL을 pipe로 전송 |
| `run_migration.yml:34-35` | `tar czf \| ssh ec2 tar xzf` | tar 스트림 pipe |

### HIGH (긴 명령 체인)

| 파일 | 패턴 | 문제 |
|------|------|------|
| `deploy_ec2.yml:96-102` | 6개 명령 `&&` 체인 via SSH | 중간 실패 시 전체 실패 |
| `run_migration.yml:71` | `nohup ... ; cat log` | cat에서 SIGPIPE |

### MEDIUM (원격 내부 pipe)

| 파일 | 패턴 | 문제 |
|------|------|------|
| `run_migration.yml:76` | `ssh ec2 'curl \| python3'` | EC2 내부 pipe |

### SAFE (HTTP API 사용)

| 파일 | 패턴 |
|------|------|
| `test_influencer_flow.py` | `urllib.request` → orbitools API |
| `seed_pipeline_creators.py` | `requests` → orbitools API |

## 근본 해결 패턴

### Pattern A: SCP-Execute-SCP (권장)

```bash
# 1. 파일을 EC2로 전송
scp -i KEY local_file.sql ubuntu@EC2:/tmp/

# 2. EC2에서 실행 (결과를 파일로)
ssh -i KEY ubuntu@EC2 "psql ... -f /tmp/local_file.sql > /tmp/result.log 2>&1; echo \$?"

# 3. 필요시 결과 가져오기
scp -i KEY ubuntu@EC2:/tmp/result.log ./
```

### Pattern B: Heredoc to File (간단한 명령)

```bash
ssh -i KEY ubuntu@EC2 << 'REMOTE'
  cd /home/ubuntu/export_calculator
  python3 manage.py migrate --settings=export_calculator.settings.production > /tmp/migrate.log 2>&1
  echo "EXIT_CODE=$?"
REMOTE
```

### Pattern C: 스크립트 전송 후 실행 (복잡한 작업)

```bash
# 로컬에서 스크립트 생성
cat > /tmp/deploy_script.sh << 'EOF'
#!/bin/bash
set -e
cd /home/ubuntu/export_calculator
python3 manage.py migrate ...
sudo systemctl restart export_calculator
echo "DONE"
EOF

# 전송 + 실행
scp -i KEY /tmp/deploy_script.sh ubuntu@EC2:/tmp/
ssh -i KEY ubuntu@EC2 "chmod +x /tmp/deploy_script.sh && /tmp/deploy_script.sh"
```

## Claude Code 로컬 사용 시 규칙

1. **절대 `| ssh` pipe 사용 금지**
2. SSH 명령 결과가 길 수 있으면 → EC2 파일로 리다이렉트 후 SCP
3. `ssh ... "CMD"` 에서 CMD가 3줄 이상이면 → 스크립트 파일로 전송
4. SSH 실행 후 exit code 확인: `echo "EXIT=$?"`
5. Windows에서는 `/c/Windows/System32/OpenSSH/ssh.exe` 사용 (Git Bash ssh 아님)

## 수정 대상 파일

1. `.github/workflows/run_migration.yml` — pipe → SCP 패턴으로 전환
2. `.github/workflows/deploy_ec2.yml` — 명령 체인 분리
3. `tools/deploy_onzenna.py` — 이미 heredoc 패턴 사용 (양호)
4. `memory/mistakes.md` — SSH 관련 M-XXX 항목 추가
