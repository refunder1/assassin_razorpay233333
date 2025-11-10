FROM php:8.3-alpine

# Install system dependencies
RUN apk update && apk add --no-cache \
    bash \
    curl \
    git \
    zip \
    unzip

# Install PHP extensions (all required for your code)
RUN docker-php-ext-install \
    bcmath \
    curl \
    json \
    mbstring \
    sockets

# Create app directory
WORKDIR /app

# Copy your PHP files
COPY autorazorpay.php ./
COPY proxy.txt ./

# Create proxy.txt if it doesn't exist
RUN if [ ! -f proxy.txt ]; then echo "127.0.0.1:8080" > proxy.txt; fi

# Expose port (Render uses $PORT)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Start PHP server (Render provides $PORT environment variable)
CMD ["sh", "-c", "php -S 0.0.0.0:${PORT:-8080} autorazorpay.php"]
