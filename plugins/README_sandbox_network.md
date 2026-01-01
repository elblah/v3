# Network Sandbox Plugin

This plugin provides network sandboxing for shell commands using seccomp, allowing you to block network access when running AI commands unattended.

## Features

- **Network sandboxing**: Blocks all network syscalls (socket, connect, bind, etc.)
- **Lazy compilation**: Compiles the seccomp binary only when needed
- **Command**: `/snet` - Show status or toggle network blocking
- **Safe default**: Sandbox is disabled by default (network access allowed)
- **Automatic requirement checking**: Verifies libseccomp-dev and gcc are available

## Installation

1. Copy the plugin to your AI Coder plugins directory:
   ```bash
   cp plugins/sandbox_network.py .aicoder/plugins/
   ```

2. Install system requirements (Ubuntu/Debian):
   ```bash
   sudo apt update
   sudo apt install libseccomp-dev build-essential
   ```

3. Restart AI Coder - the plugin will load automatically

## Usage

```bash
# Show current sandbox status
/snet

# Enable network sandboxing
/snet on

# Disable network sandboxing  
/snet off

# Show help
/snet help
```

## How It Works

1. **When enabled**: All `run_shell_command` calls are wrapped with a seccomp binary that blocks network syscalls
2. **Compilation**: The seccomp C program is compiled on-demand (only when first needed) and cached in `/tmp`
3. **Binary location**: The compiled executable is stored as `/tmp/block-net-aicoder` for reuse
4. **Command wrapping**: Original commands are executed as: `block-net-aicoder bash -c "your-command"`

## Security

The plugin blocks these network-related syscalls:
- `socket` - Create socket
- `connect` - Connect to remote host
- `bind` - Bind socket to address
- `listen` - Listen for connections
- `accept`/`accept4` - Accept connections
- `sendto`/`recvfrom` - Send/receive data
- `sendmsg`/`recvmsg`/`sendmmsg`/`recvmmsg` - Message operations
- `socketcall` - Socket system call multiplexer

## Requirements

### System Requirements
- Linux with seccomp support (most modern distributions)
- GCC compiler
- libseccomp development headers

### Installation Commands

**Ubuntu/Debian:**
```bash
sudo apt install libseccomp-dev build-essential
```

**Fedora/CentOS/RHEL:**
```bash
sudo dnf install libseccomp-devel gcc make
```

**Arch Linux:**
```bash
sudo pacman -S libseccomp gcc make
```

## Use Cases

### When to Enable Network Sandbox

- **Unattended operations**: When leaving AI working alone for extended periods
- **Security-sensitive environments**: When network access should be restricted
- **Testing offline workflows**: When you want to ensure code works without network dependencies
- **Preventing accidental network calls**: When working with code that shouldn't access the internet

### Example Workflow

```bash
# Start AI Coder (network access available by default)
$ aicoder

# Enable network sandbox before leaving AI unattended
User: /snet on
AI: [+] Network sandbox enabled
     [INFO] Seccomp binary will be compiled on first shell command

# AI can now execute commands safely without network access
User: Write a script that processes local files
AI: [writes script]
AI: Let me test it:
AI: run_shell_command(command="./process_files.sh")
    [Network sandbox blocks any network attempts in the script]
    
# Disable when you need network access again
User: /snet off
AI: [-] Network sandbox disabled
```

## Troubleshooting

### Missing Requirements

If you see errors about missing requirements:

```bash
[X] Network sandbox unavailable - missing requirements:
    - libseccomp-dev (install with: apt install libseccomp-dev)
    - gcc (install with: apt install build-essential)
```

Install the missing packages and try enabling the sandbox again.

### Seccomp Binary Not Found

If the compiled binary is removed from `/tmp`, the plugin will automatically recompile it on the next shell command.

### Permission Issues

The plugin needs write access to `/tmp` to store the compiled binary. This should be available on most systems.
