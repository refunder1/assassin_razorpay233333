FROM php:8.3-alpine

# Install system dependencies FIRST
RUN apk update && apk add --no-cache \
    bash \
    curl \
    git \
    zip \
    unzip \
    # Required for PHP extensions
    libcurl \
    curl-dev \
    libzip-dev \
    zlib-dev \
    libpng-dev \
    libjpeg-turbo-dev \
    freetype-dev \
    libxml2-dev \
    oniguruma-dev

# Install PHP extensions (with dependencies available)
RUN docker-php-ext-install \
    bcmath \
    mbstring \
    sockets \
    json \
    xml

# Install curl extension separately with proper dependencies
RUN apk add --no-cache curl-dev && \
    docker-php-ext-install curl

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
    CMD curl -f http://localhost:${PORT:-8080}/ || exit 1

# Start PHP server (Render provides $PORT environment variable)
CMD ["sh", "-c", "php -S 0.0.0.0:${PORT:-8080} autorazorpay.php"]
