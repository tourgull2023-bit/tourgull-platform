FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build && chown -R node:node /app
USER node
EXPOSE 3000
ENV HOST=0.0.0.0 PORT=3000
CMD ["node", "build"]
