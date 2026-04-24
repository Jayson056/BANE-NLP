#ifndef BANE_CONFIG_H
#define BANE_CONFIG_H

// BANE NLP NATIVE CONFIGURATION
#define BNP_VERSION "2.0-C-NATIVE"

// PORT CONFIGURATION
#define WEBHOOK_PORT 8080
#define PYTHON_BRIDGE_PORT 5000

// SECURITY
#define VERIFY_TOKEN "bane_messenger_secure_777"
#define RATE_LIMIT_SEC 60
#define MAX_REQUESTS_PER_MIN 20

// PATHS
#define LOG_PATH "logs/bnp_native.log"
#define DATA_PATH "core/bane_data.db"

#endif
