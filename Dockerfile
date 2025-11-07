# 1. Base Image: Start with a Python image, using a slim version for smaller size.
FROM python:3.11-slim

# 2. Working Directory: Set the directory inside the container where the app will live.
WORKDIR /usr/src/app

# 3. Dependencies: Copy the requirements file and install dependencies.
# This relies on you having a 'requirements.txt' file with 'discord.py' and 'docker' listed.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 4. Code: Copy your entire project into the working directory.
COPY . .

# 5. Command: Define the entry point for the container.
CMD [ "python", "bot.py" ]