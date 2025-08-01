# 前端 Dockerfile
FROM node:18-alpine

# 設定工作目錄
WORKDIR /app

# 複製 package.json 和 package-lock.json
COPY package*.json ./

# 安裝依賴
RUN npm install

# 複製所有前端檔案
COPY . .

# 暴露端口
EXPOSE 3000

# 啟動開發服務器
CMD ["npm", "start"]