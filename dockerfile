FROM php:8.3-alpine

# Copy your PHP files
COPY autorazorpay.php /app/
COPY proxy.txt /app/

# Set working directory
WORKDIR /app

# Create proxy.txt if missing
RUN if [ ! -f proxy.txt ]; then echo "127.0.0.1:8080" > proxy.txt; fi

# Expose port
EXPOSE 8080

# Start PHP server
CMD ["sh", "-c", "php -S 0.0.0.0:${PORT:-8080} autorazorpay.php"]
