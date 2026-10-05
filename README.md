# book-to-course

Turn a book into an interactive course you can run locally in a browser. This Claude skill uses the source material to build beginner-friendly lessons, then adds ways to practise and check what you have learned. It accepts EPUB, PDF, HTML, DOCX, Markdown, and plain text.

## What a course can include

- Short lessons with step-by-step explanations, worked examples, diagrams, and animated walkthroughs.
- Interactive quizzes with hints and explanations, chapter tests, and flashcards.
- Programming exercises with starter code, examples, and unit tests. Learners write code in their editor, run the tests from the course page, and see whether their solution passes.
- Progress tracking for lessons, quiz answers, and exercises, saved locally so learners can pick up where they left off.

For coding exercises, the skill checks that the tests fail on the starter code and pass on a reference solution before packaging the course. When a book does not call for code, the course can use other practice activities, such as self-check exercises.

## Demo

A Go programming course: an animated code walkthrough, a quiz, flashcards, and an exercise whose unit tests run from the page.

![Demo of a Go course: code walkthrough, quiz, flashcards and passing exercise tests](doc/gifs/go-course-demo.gif)

A math course: formulas written in LaTeX render in lesson text, tables, quizzes, and flashcards.

![Demo of a math course with rendered formulas, a quiz and flashcards](doc/gifs/math-course-demo.gif)

## Installation

This repository is a [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) plugin marketplace. In Claude Code, add the marketplace and install the plugin:

```
/plugin marketplace add sebastianhaba/book-to-course-skill
/plugin install book-to-course@book-to-course
```

Then attach a book and ask Claude to turn it into a course, for example: *"Turn this book into an interactive course."*

To update to the latest version later, run `/plugin marketplace update book-to-course`.

## Example course

These screenshots show a course generated from a Go programming book:

### Course overview and progress

![Course overview with chapters and progress](doc/img/go_course_1.png)

### Interactive quiz

![Quiz with answer choices and hints](doc/img/go_course_2.png)

### Coding exercise and test results

![Coding exercise with starter code and a Run tests button](doc/img/go_course_3.png)

## How it works

1. Give the skill a book or document and ask it to create a course. You can specify the course language and scope.
2. The skill extracts the source, plans lessons by chapter, and builds the course as a folder of local web files.
3. Open the generated course with `start.sh` (macOS/Linux) or `start.bat` (Windows). The local server saves progress to `progress/progress.json` and lets the **Run tests** button execute the exercise's test command on your computer.

Starting the course this way requires Python 3. Programming exercises also require the relevant language and test tools, such as Go for a Go course. You can open `index.html` directly without the server; quizzes and lessons still work, while progress stays in the browser and code tests must be run in a terminal.

The skill and its supporting scripts, templates, and references are in [`book-to-course/`](book-to-course/SKILL.md). Generated courses are self-contained folders that can be packaged and shared.

## Course on a phone or tablet (Android)

The second skill in this plugin, [`course-to-apk`](course-to-apk/SKILL.md), packages a generated course as a small offline Android app. Ask, for example: *"Make an APK of this course for my tablet."*

- The app is a lightweight WebView wrapper: the course is bundled inside the APK, works without internet access, and keeps progress on the device across updates. It runs on Android 7.0 and newer.
- The APK is built straight from the Android SDK tools with no Gradle or Android Studio project, and signed with the Android debug key (`~/.android/debug.keystore`). You can also sign it with your own keystore.
- Building requires JDK 17+ and Android SDK build-tools plus a platform package. The skill checks for them first. If something is missing, it tells you what to download and where to get it, then either waits for you to install it or downloads it into `~/.local/share/course-to-apk` with your consent (no sudo).
- The output goes next to the course, in `<course>-android/`. Copy the APK to the device and open it, or install it over USB with `adb`.

Code exercises can't run their unit tests on a phone, so use the computer version for those. Lessons, quizzes, tests, and flashcards all work in the app.

## Course as a Linux desktop app (AppImage)

The third skill, [`course-to-appimage`](course-to-appimage/SKILL.md), packages a generated course as a single, self-contained AppImage. Copy the file to any desktop Linux computer and start it; nothing else needs to be installed. Ask, for example: *"Make an AppImage of this course so I can open it from the app menu."*

- The app wraps the course in its own WebView engine, the official Electron build of Chromium and Node.js. Nothing is compiled. It also carries a colour emoji font, so emoji display even on systems without one. The AppImage is about 115 MB plus the size of the course, and it runs on current desktop distributions.
- Progress is saved to `~/.local/share/<app-id>/` and kept across updates.
- Programming exercises work as in the folder version, unlike on a phone, because the AppImage runs as a normal program on your computer. The app copies the exercises to `~/.local/share/<app-id>/exercises/`, and each exercise shows its full folder path with an **Open folder** button. Edit the files in your own editor, then use the **Run tests** button to run their unit tests with the compiler installed on the computer. The exercise's language tools, such as Go, must be installed.
- Building requires `appimagetool`, Electron (a one-time download of about 115 MB), and the Noto Color Emoji font, which is usually already installed. The AppImage runtime file is also needed if you want to build offline. The skill checks for them first. If something is missing, it tells you what to download and where to get it, then either waits for you to install it or downloads it into `~/.local/share/course-to-appimage` with your consent (no sudo, checksums verified).
- The output goes next to the course, in `<course>-appimage/`. Start the file directly, or have the skill add it to your application menu, which copies it to `~/Applications`.

## License

Released under the [MIT License](LICENSE).
