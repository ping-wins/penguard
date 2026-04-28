FROM node:22-alpine

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH

RUN corepack enable && corepack prepare pnpm@10.33.2 --activate

WORKDIR /app

EXPOSE 5173

CMD ["pnpm", "--filter", "@fortidashboard/web", "dev", "--host", "0.0.0.0"]
