#define NOB_IMPLEMENTATION
#define NOB_STRIP_PREFIX
#include "nob.h"

Cmd cmd = {0};

int main(int argc, char **argv)
{
    NOB_GO_REBUILD_URSELF(argc, argv);
    cmd_append(&cmd, "cc");
    cmd_append(&cmd, "-Wall");
    cmd_append(&cmd, "-Wextra");
    cmd_append(&cmd, "-g");
    cmd_append(&cmd, "-o", "main", "main.c");

#ifdef __APPLE__
    // macOS: Use Homebrew-installed raylib
    cmd_append(&cmd, "-I/opt/homebrew/include");
    cmd_append(&cmd, "-L/opt/homebrew/lib");
    cmd_append(&cmd, "-lraylib");
    // macOS frameworks required by raylib
    cmd_append(&cmd, "-framework", "OpenGL");
    cmd_append(&cmd, "-framework", "Cocoa");
    cmd_append(&cmd, "-framework", "IOKit");
    cmd_append(&cmd, "-framework", "CoreVideo");
#else
    // Linux: Use bundled raylib
    cmd_append(&cmd, "-I./raylib-5.5_macOs/include/");
    cmd_append(&cmd, "-L./raylib-5.5_macOs/lib/");
    cmd_append(&cmd, "-l:libraylib.a");
    cmd_append(&cmd, "-lm");
#endif

    if (!cmd_run(&cmd)) return 1;
    return 0;
}
