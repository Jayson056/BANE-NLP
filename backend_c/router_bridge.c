#include <stdio.h>
#include <winsock2.h>
#include "json_parser.h"

/**
 * Forwards a validated webhook payload to the BANE Python engine.
 * Python Engine (Port 5000) -> MessengerBot._process_async
 */
int forward_to_python_engine(const char* payload) {
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2, 2), &wsaData);

    SOCKET sock = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in serv_addr;
    serv_addr.sin_family = AF_INET;
    serv_addr.sin_port = htons(5000);
    serv_addr.sin_addr.s_addr = inet_addr("127.0.0.1");

    if (connect(sock, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) < 0) {
        printf("BRIDGE ERROR: Python Engine (Port 5000) not reachable.\n");
        closesocket(sock);
        return -1;
    }

    // Construct a raw HTTP POST for the internal bridge
    char request[8192];
    sprintf(request, 
        "POST /webhooks/messenger HTTP/1.1\r\n"
        "Host: localhost\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: %zu\r\n"
        "\r\n"
        "%s", 
        strlen(payload), payload);

    send(sock, request, (int)strlen(request), 0);
    
    closesocket(sock);
    return 0;
}
