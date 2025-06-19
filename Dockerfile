# 1. Use an official Python image
FROM python:3.11-slim

# 2. Set the working directory
WORKDIR /app

# 3. Copy dependency list and install
COPY requirements.txt .
COPY bot.py .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy the rest of your code
COPY . .

# 5. Set the command to run your bot
CMD ["python", "bot.py"]
