FROM python:3.12-slim

# Set timezone to JST (scheduler depends on JST)
ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Run scheduler daemon
CMD ["python", "tools/twitter_scheduler.py", "--daemon"]
