#import <Cocoa/Cocoa.h>
#include <stdlib.h>
#include <unistd.h>
#include <libgen.h>
#include <string.h>

int main(int argc, char *argv[]) {
    @autoreleasepool {
        // 设置环境变量
        setenv("PATH", "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", 1);
        setenv("LANG", "en_US.UTF-8", 1);

        // 项目路径
        const char *project_dir = "/Users/nqt/my-whisper";

        // 构建 venv python 路径和脚本路径
        char python_path[1024];
        char script_path[1024];
        char activate_cmd[2048];

        snprintf(python_path, sizeof(python_path), "%s/venv/bin/python", project_dir);
        snprintf(script_path, sizeof(script_path), "%s/main.py", project_dir);

        // 设置 VIRTUAL_ENV 环境变量
        char venv_path[1024];
        snprintf(venv_path, sizeof(venv_path), "%s/venv", project_dir);
        setenv("VIRTUAL_ENV", venv_path, 1);

        // 将 venv/bin 添加到 PATH 前面
        char new_path[4096];
        snprintf(new_path, sizeof(new_path), "%s/venv/bin:%s",
                 project_dir, getenv("PATH") ?: "");
        setenv("PATH", new_path, 1);

        // exec Python
        char *args[] = { python_path, script_path, NULL };
        execv(python_path, args);

        // 如果 exec 失败
        NSLog(@"My Whisper: 启动 Python 失败");
        return 1;
    }
}
