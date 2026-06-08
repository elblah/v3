CC = gcc
CFLAGS = -O2 -Wall -Wextra
TARGET = stats_server

all: $(TARGET)

$(TARGET): stats_server.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f $(TARGET)

.PHONY: all clean
