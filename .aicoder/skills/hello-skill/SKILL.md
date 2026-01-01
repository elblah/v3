---
name: hello-skill
description: Demonstrates simple script execution. Use this skill when you need to execute the hello-world script or test the skills plugin's script execution capabilities.
---

# Hello World Skill

This skill demonstrates how to create and execute simple scripts within the skills system.

## When to Use

Use this skill when:
- Testing the skills plugin functionality
- Verifying that scripts can be discovered and executed
- Demonstrating script execution to users
- Learning how skills work with scripts

## Available Script

The `hello-world.sh` script is located in `scripts/hello-world.sh` and prints a friendly greeting message.

## How to Use

When a user asks for a demonstration, greeting, or wants to test the skill system:

1. Execute the script using: `run_shell_command` with the path to the script
2. The script will output a greeting message
3. Present the output to the user in a friendly way

## Script Details

- **Path**: `scripts/hello-world.sh`
- **Purpose**: Demonstrates that skills can include executable scripts
- **Usage**: Run it via shell command execution
- **Output**: Prints a greeting message

## Example Prompts

- "Show me the hello skill in action"
- "Test the skills system"
- "Run a demonstration script"
- "I want to see what the hello skill does"
