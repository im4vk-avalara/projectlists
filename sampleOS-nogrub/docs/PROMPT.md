You are an expert operating-system architect, compiler/runtime engineer, and AI systems designer.

I want to build an experimental AI-native operating system that runs in QEMU. The OS should have AI capability built into the OS image itself, not merely as an external desktop application. However, the AI logic should not run inside the kernel. It should be implemented as a core user-space system service/daemon that communicates with the kernel, shell, app runtime, filesystem, and sandbox manager.

Design a complete technical plan for this OS.

Project goal:
Build a toy but extensible AI-native OS where a user can type natural-language commands such as:

* “Create a calculator app”
* “Create a notes app that saves files”
* “Modify the notes app to support search”
* “Debug this app crash”
* “Generate a UI for a todo manager”

The OS should use an AI SDK or AI model client built into a native system service called `ai-daemon`. The daemon may initially call a cloud AI API over the network, but the architecture should allow replacing or supplementing it later with a local model runtime.

Core requirement:
The AI must never generate or execute unrestricted kernel code. AI-generated output must be validated and run only as sandboxed user-space apps, interpreted DSL, bytecode, or WebAssembly-style modules.

Design constraints:

* Target emulator: QEMU
* Initial architecture: x86 or x86_64
* Boot approach: GRUB/Multiboot or another practical bootloader
* Kernel language: C, C++, or Rust
* User-space services allowed
* AI SDK integrated into the OS image as part of `ai-daemon`
* Generated apps must run with strict permissions
* Kernel must remain stable even if AI output is invalid
* First prototype should be simple and achievable

Please provide:

1. A high-level architecture diagram in text form.
2. The recommended module breakdown:

   * kernel
   * shell
   * ai-daemon
   * app-builder
   * validator
   * app runtime
   * sandbox manager
   * filesystem
   * networking
3. A phased development roadmap from “boot in QEMU” to “AI-generated apps.”
4. A recommended first prototype scope.
5. The design of the AI app format, preferably JSON schema or a small custom DSL.
6. Example AI-generated app definition for a calculator app.
7. Example validator rules.
8. Example syscall/API surface exposed to sandboxed apps.
9. How `ai-daemon` should communicate with:

   * shell
   * filesystem
   * app runtime
   * network stack
   * AI SDK/API
10. Security and safety model.
11. Failure handling strategy for hallucinated or invalid AI output.
12. Suggested file and directory structure for the project.
13. Example build/run commands for QEMU.
14. What not to do, especially regarding AI-generated kernel code.
15. Future upgrade path for local offline AI models.

The answer should be practical, engineering-focused, and organized as a build plan. Avoid vague hype. Assume I want to actually start implementing this as a hobby/research OS.
