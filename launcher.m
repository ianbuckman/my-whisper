#import <Cocoa/Cocoa.h>
#include <stdlib.h>
#include <unistd.h>
#include <libgen.h>
#include <string.h>
#include <mach-o/dyld.h>

int main(int argc, char *argv[]) {
    @autoreleasepool {
        setenv("LANG", "en_US.UTF-8", 1);

        // 获取 launcher 的绝对路径（.app/Contents/MacOS/launcher）
        char exe_path[4096];
        uint32_t size = sizeof(exe_path);
        if (_NSGetExecutablePath(exe_path, &size) != 0) {
            NSLog(@"My Whisper: 无法获取可执行文件路径");
            return 1;
        }

        // 向上两级：MacOS → Contents → Resources
        char tmp[4096];
        strlcpy(tmp, exe_path, sizeof(tmp));
        char *macos_dir = dirname(tmp);          // .../Contents/MacOS
        char contents_dir[4096];
        strlcpy(contents_dir, macos_dir, sizeof(contents_dir));
        char *contents_parent = dirname(contents_dir);  // .../Contents
        char resources_dir[4096];
        snprintf(resources_dir, sizeof(resources_dir), "%s/Resources", contents_parent);

        // 优先尝试 bundle 内的 venv（适合分发）
        char python_path[4096];
        char script_path[4096];
        char venv_path[4096];
        char venv_bin[4096];

        snprintf(python_path, sizeof(python_path), "%s/venv/bin/python", resources_dir);
        snprintf(script_path, sizeof(script_path), "%s/main.py", resources_dir);
        snprintf(venv_path, sizeof(venv_path), "%s/venv", resources_dir);
        snprintf(venv_bin, sizeof(venv_bin), "%s/venv/bin", resources_dir);

        // Fallback：bundle 内没有 venv 时，用开发机的项目目录
        if (access(python_path, X_OK) != 0) {
            const char *dev_dir = "/Users/nqt/my-whisper";
            snprintf(python_path, sizeof(python_path), "%s/venv/bin/python", dev_dir);
            snprintf(script_path, sizeof(script_path), "%s/main.py", dev_dir);
            snprintf(venv_path, sizeof(venv_path), "%s/venv", dev_dir);
            snprintf(venv_bin, sizeof(venv_bin), "%s/venv/bin", dev_dir);
        }

        setenv("VIRTUAL_ENV", venv_path, 1);
        char new_path[8192];
        snprintf(new_path, sizeof(new_path),
                 "%s:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                 venv_bin);
        setenv("PATH", new_path, 1);

        chdir(resources_dir);

        NSLog(@"My Whisper: launching python=%s script=%s", python_path, script_path);
        char *args[] = { python_path, script_path, NULL };
        execv(python_path, args);

        NSLog(@"My Whisper: execv 失败 python_path=%s", python_path);
        return 1;
    }
}
