FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/uploads

EXPOSE 8000

# Who may tell uvicorn the real client address. The API always sits behind
# nginx, so without this every request looks like it came from the proxy:
# rate limits become one bucket shared by every user, and audit rows carry the
# proxy's IP. Trusted = the private ranges Docker allocates bridge networks
# from (172.16/12, 192.168/16) plus loopback — i.e. the nginx container and,
# for a host-level TLS proxy, the bridge gateway. Not '*': with '*' uvicorn
# takes the LEFT-most X-Forwarded-For entry, which any client can write.
# With a list it walks right-to-left and stops at the first untrusted hop,
# the one nginx itself appended. If a proxy outside these ranges fronts the
# portal, add its address via the FORWARDED_ALLOW_IPS env var.
ENV FORWARDED_ALLOW_IPS="172.16.0.0/12,192.168.0.0/16,127.0.0.1"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
