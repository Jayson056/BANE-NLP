#include <stdio.h>
#include <stdlib.h>
#include <windows.h>
#include <time.h>

#define LOG_FILE "logs/bnp_native.log"

void clear_screen() {
    system("cls");
}

void print_header() {
    printf("\033[1;34m====================================================\033[0m\n");
    printf("\033[1;36m       BANE NLP NATIVE C-DASHBOARD (v2.0-C)       \033[0m\n");
    printf("\033[1;34m====================================================\033[0m\n");
    time_t now;
    time(&now);
    printf(" SYSTEM TIME: %s", ctime(&now));
    printf(" STATUS     : \033[1;32mOPERATIONAL (HIGH SPEED)\033[0m\n");
    printf("----------------------------------------------------\n\n");
}

void tail_logs() {
    FILE* f = fopen(LOG_FILE, "r");
    if (!f) {
        printf("\033[1;31m[!] Waiting for log data...\033[0m\n");
        return;
    }

    fseek(f, -500, SEEK_END); // Read last 500 bytes
    char line[256];
    printf("\033[1;33mRECENT ACTIVITY:\033[0m\n");
    while (fgets(line, sizeof(line), f)) {
        if (strstr(line, "[SERVER]")) printf("\033[0;32m %s", line);
        else if (strstr(line, "[SECURITY]")) printf("\033[0;35m %s", line);
        else if (strstr(line, "[ROUTER]")) printf("\033[0;36m %s", line);
        else printf("\033[0;37m %s", line);
    }
    fclose(f);
}

int main() {
    // Enable ANSI support in Windows console
    HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD dwMode = 0;
    GetConsoleMode(hOut, &dwMode);
    dwMode |= ENABLE_VIRTUAL_TERMINAL_PROCESSING;
    SetConsoleMode(hOut, dwMode);

    while (1) {
        clear_screen();
        print_header();
        tail_logs();
        printf("\n\033[0;90m(Press Ctrl+C to exit dashboard)\033[0m");
        Sleep(1000); // Refresh every second
    }
    return 0;
}
