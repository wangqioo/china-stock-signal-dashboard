FROM python:3.11-slim

WORKDIR /app

# 换国内镜像源加速
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 复制代码
COPY . .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 建立必要目录
RUN mkdir -p logs data dashboard

EXPOSE 8877

CMD ["python", "server.py"]
