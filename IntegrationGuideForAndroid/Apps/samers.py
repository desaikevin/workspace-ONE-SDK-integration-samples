# Copyright 2020 VMware, Inc.
# SPDX-License-Identifier: BSD-2-Clause

# Run with Python 3.7
"""Script to check duplication of source files and resources."""
#
# Standard library imports, in alphabetic order.
#
# Module for command line switches.
# Tutorial: https://docs.python.org/3/howto/argparse.html
# Reference: https://docs.python.org/3/library/argparse.html
import argparse
#
# Sequence comparison module.
# https://docs.python.org/3/library/difflib.html#difflib.context_diff
from difflib import context_diff
#
# Module for old school paths. Only used to get commonpath(), which doesn't have
# an equivalent in OO paths.
# https://docs.python.org/3/library/os.path.html
import os.path
#
# Module for OO path handling.
# https://docs.python.org/3/library/pathlib.html
from pathlib import Path
#
# Module for file and directory handling.
# https://docs.python.org/3.5/library/shutil.html
import shutil
#
# Module for spawning a process to run a command.
# https://docs.python.org/3/library/subprocess.html
import subprocess
#
# Module for getting the command line.
# https://docs.python.org/3/library/sys.html
import sys
#
# Temporary file module.
# https://docs.python.org/3/library/tempfile.html
from tempfile import NamedTemporaryFile
#
# Module for text dedentation.
# Only used for --help description.
# https://docs.python.org/3/library/textwrap.html
import textwrap

def glob_each(path, patterns):
    for pattern in patterns:
        matches = []
        for match in path.glob(pattern):
            matches.append(match)
            yield match

        if len(matches) == 0:
            raise ValueError(f'Failed, no match for "{pattern}".')
        if len(matches) == 1:
            raise ValueError(
                f'Failed, only one match for "{pattern}": {matches[0]}.')

class Rules:

    # Maybe some uncommon Python syntax here:
    #
    # -   Function parameters have leading * to make them be a vararg type of
    #     list.
    # -   Format string, aka f-string, with interpolated values.
    # -   Nested list comprehensions, but without any parentheses.
    #
    # Where the function is called, it is prefixed with another *, as the spread
    # operator.
    def _java_kt(*stubs):
        return [
            f'**/{stub}.{extension}'
            for stub in stubs
            for extension in ('java', 'kt')
        ]

    # Patterns that match AndroidManifest.xml have /main/ to prevent matching
    # intermediate manifests under the build directory.
    simplePatterns = [
        # Deliberate failures.
        'nuffin', 'samers*',

        # Files that should be the same everywhere.
        '**/proguard-rules.pro', '**/buildBase.gradle',
        '**/downloadClient.gradle', '**/integrateClient.gradle',
        '**/downloadFramework.gradle', '**/integrateFramework.gradle',
        *_java_kt(
            'AirWatchSDKIntentService', 'BaseActivity', 'Application',
            'AWApplication', 'BrandingManager', 'BitmapBrandingManager'
        ),

        # Commented out because there's only one of each.
        # '**/DynamicBrandApplication.java', '**/DynamicBrandApplication.kt',

        # build.gradle files that aren't the same as the framework.
        # Pre-framework builds have different dependencies. Branding builds set
        # different ApplicationClass values.
        'base*/build.gradle', 'client*/build.gradle',
        'brandDynamicDelegate*/build.gradle',
        'brandDynamicExtend*/build.gradle',
        'brandEnterprise*Delegate*/**/build.gradle',
        'brandEnterprise*Extend*/**/build.gradle',

        # XML files that can have a simple pattern.
        'brandStatic*/**/styles.xml', 'brandDynamic*/**/strings.xml',

        # Pre-Framework Android manifests.
        'base*/**/main/AndroidManifest.xml',
        'client*/**/main/AndroidManifest.xml',

        # MainActivity classes that aren't the same as the framework.
        'brandDynamic*Java/**/MainActivity.java',
        'brandDynamic*Kotlin/**/MainActivity.kt'
    ]

    namedPatternLists = {
        "unbranded styles.xml files": [
            'base*/**/styles.xml',
            'client*/**/styles.xml',
            'framework*/**/styles.xml'
        ],

        "unbranded strings.xml files": [
            'base*/**/strings.xml',
            'client*/**/strings.xml',
            'framework*/**/strings.xml',
            'brandEnterpriseOnly*/**/strings.xml'
        ],
        "application branded strings.xml files": [
            'brandStatic*/**/strings.xml',
            'brandEnterprisePriority*/**/strings.xml'
        ],

        "framework manifests": [
            'framework*/**/main/AndroidManifest.xml',
            'brand*/**/main/AndroidManifest.xml'
        ],
        "framework build.gradle files": [
            'frameworkExtend*/**/build.gradle',
            'brandStaticExtend*/**/build.gradle'
        ],
        "base MainActivity.java files": [
            'framework*/**/MainActivity.java',
            'brandEnterprise*/**/MainActivity.java',
            'brandStatic*/**/MainActivity.java'
        ],
        "base MainActivity.kt files": [
            'framework*/**/MainActivity.kt',
            'brandEnterprise*/**/MainActivity.kt',
            'brandStatic*/**/MainActivity.kt'
        ]
    }

    # ToDo: Directory trees that should be the same
    # 'appBase*/src/main/',

    def __init__(self, topPath):
        super()
        self._topPath = topPath

    @classmethod
    def named_lists(cls):
        for simplePattern in cls.simplePatterns:
            yield f'"{simplePattern}"', [simplePattern]

        for description, patterns in cls.namedPatternLists.items():
            yield description, patterns
    
    def named_globs(self):
        for description, patterns in self.named_lists():
            yield description, glob_each(self._topPath, patterns)

    def patterns_matched_by(self, targetPath):
        for description, patterns in self.named_lists():
            matched = False
            for pattern in patterns:
                for path in self._topPath.glob(pattern):
                    if path == targetPath:
                        matched = True
                        break
            if matched:
                yield description, patterns
                break

# Jim had hoped to code the patterns_matched_by method without having to glob
# out every pattern. It didn't work, see following transcript.
#
#     $ python3
#     Python 3.7.2 (v3.7.2:9a3ffc0492, Dec 24 2018, 02:44:43) 
#     [Clang 6.0 (clang-600.0.57)] on darwin
#     Type "help", "copyright", "credits" or "license" for more information.
#     >>> from pathlib import Path
#     >>> ori = Path('baseKotlin/src/main/res/values/styles.xml')
#     >>> ori
#     PosixPath('baseKotlin/src/main/res/values/styles.xml')
#     >>> ori.match('styles.xml')
#     True
#     >>> ori.match('*styles.xml')
#     True
#     >>> ori.match('**/styles.xml')
#     True
#     >>> ori.match('base*/**/styles.xml')
#     False

def diff_each(paths, pathLeft=None):

    linesLeft = None
    if pathLeft is not None:
        with pathLeft.open() as file:
            linesLeft = file.readlines()

    for path in paths:
        with path.open() as file:
            lines = file.readlines()

        if pathLeft is None:
            pathLeft = path
            linesLeft = lines
            continue
        
        if path == pathLeft:
            continue
        
        differences = [diff for diff in context_diff(
            linesLeft, lines, fromfile=str(pathLeft), tofile=str(path)
        )]
        
        yield pathLeft, path, differences if len(differences) > 0 else None


class NoticesEditor:
    _leader_suffixes_map = {
        "#": ['.gitignore', '.pro', '.properties', '.py'],
        "//": ['.gradle', '.java', '.kt']
    }

    _exempt_suffixes = ['.png']

    _custom_suffixes_map = {'.xml': 'xml_editor'}
    
    def __init__(self, noticesPath):
        self._noticesPath = Path(noticesPath)
        with self._noticesPath.open() as noticesFile: self._noticesLines = [
            line.strip() for line in noticesFile.readlines()]
        self._noticesXML = "\n".join((
            "<!--", *["    " + line for line in self._noticesLines], "-->\n"))

    def check(self, path):
        path = Path(path)
        suffix = self._effective_suffix(path)

        if suffix in self._exempt_suffixes:
            return True, None

        linesFound = 0
        with path.open('r') as file:
            for line in file:
                try:
                    if line.find(self._noticesLines[linesFound]) >= 0:
                        linesFound += 1
                        # print(linesFound, line)
                except IndexError:
                    # By now, linesFound is one more than the index of the last
                    # line in the notices. That happens to be the same as the
                    # number of lines in the notices.
                    return True, linesFound

        return False, linesFound

    @staticmethod
    def _effective_suffix(path):
        if path.suffix == "" and path.name.startswith("."):
            return path.name
        return path.suffix

    def insert(self, originalPath):
        editedPath = None
        originalPath = Path(originalPath)
        suffix = self._effective_suffix(originalPath)

        try:
            customEditorName = self._custom_suffixes_map[suffix]
            # Next line sets customEditor to the bound method.
            customEditor = getattr(self, customEditorName)
        except KeyError:
            customEditor = None

        for key, suffixList in self._leader_suffixes_map.items():
            if suffix in suffixList:
                commentLead = key
                break

        with NamedTemporaryFile(
                mode='wt', delete=False
                , prefix=originalPath.stem + '_', suffix=originalPath.suffix
            ) as editedFile, \
            originalPath.open('rt') as originalFile \
        :
            editedPath = Path(editedFile.name)
            if customEditor is None:
                self._leader_editor(commentLead, originalFile, editedFile)
            else:
                customEditor(originalFile, editedFile)

        return editedPath, self._editor_differences(originalPath, editedPath)
    
    # Simple editor that inserts the notices at the start of the file.
    #
    # Each notice line is prefixed by a specified leader and a space.  
    # If the first line of the original file wasn't a blank line, then a blank
    # line is inserted after the notice lines.  
    # Then append the rest of the original file.
    def _leader_editor(self, commentLead, originalFile, editedFile):
        for line in self._noticesLines:
            editedFile.write(commentLead)
            editedFile.write(" ")
            editedFile.write(line)
            editedFile.write("\n")

        for index, line in enumerate(originalFile):
            if index == 0 and line.strip() != "":
                editedFile.write("\n")
            editedFile.write(line)
    
    def _editor_differences(self, originalPath, editedPath):
        with originalPath.open() as file: originalLines = file.readlines()
        with editedPath.open() as file: editedLines = file.readlines()

        return [diff for diff in context_diff(
            originalLines, editedLines,
            fromfile=str(originalPath), tofile="Edited"
        )]

    # Custom editor for XML files.
    #
    # If the first line is an XML declaration, put the notices XML comment after
    # it. Otherwise, put the notices first. Then append the rest of the file
    # unchanged.
    #
    # Simple way to identify the XML declaration is that it starts `<?xml`.
    #
    # This code mightn't behave correctly if the xml file is empty. That
    # probably isn't valid XML anyway.
    def xml_editor(self, originalFile, editedFile):
        line = originalFile.readline()
        if line.startswith("<?xml"):
            editedFile.write(line)
            editedFile.write(self._noticesXML)
        else:
            editedFile.write(self._noticesXML)
            editedFile.write(line)
        line = originalFile.readline()
        while line != '':
            editedFile.write(line)
            line = originalFile.readline()

        # Following code would do something more fancy. It looks for the first
        # end tag, `>` character, and then inserts the notice XML comment after
        # it. The output wasn't as clean, and is different to what Jim did in
        # another Open Source repository, so it's commented out.
        #
        # inserted = False
        # while line != '':
        #     if inserted:
        #         editedFile.write(line)
        #     else:
        #         partition = line.partition('>')
        #         editedFile.write(partition[0])
        #         editedFile.write(partition[1])
        #         if partition[1] != '':
        #             if partition[0].endswith("?"):
        #                 editedFile.write("\n")
        #             editedFile.write("\n".join((
        #                 "<!--", *self._noticesLines, "-->"
        #             )))
        #             inserted = True
        #         editedFile.write(partition[2])
        #     line = originalFile.readline()

class DuplicatorJob:

    # Properties that are set by the CLI.
    #
    @property
    def counting(self):
        return self._counting
    @counting.setter
    def counting(self, counting):
        self._counting = counting

    @property
    def insertNotices(self):
        return self._insertNotices
    @insertNotices.setter
    def insertNotices(self, insertNotices):
        self._insertNotices = insertNotices

    @property
    def notices(self):
        return self._notices
    @notices.setter
    def notices(self, notices):
        self._notices = notices
        self._noticesPath = Path(notices)

    @property
    def originals(self):
        return self._originals
    @originals.setter
    def originals(self, originals):
        self._originals = originals

    @property
    def top(self):
        return self._top
    @top.setter
    def top(self, top):
        self._top = top
        self._topPath = Path(top)

    @property
    def verbose(self):
        return self._verbose
    @verbose.setter
    def verbose(self, verbose):
        self._verbose = verbose

    @property
    def yes(self):
        return self._yes
    @yes.setter
    def yes(self, yes):
        self._yes = yes
    #
    # End of CLI propperties.

    def __call__(self):
        self._rules = Rules(self._topPath)
        self._noticesEditor = (
            NoticesEditor(self._noticesPath) if self.insertNotices else None)

        originalsChecked = 0
        edited = 0
        for original in self.originals:
            originalsChecked += 1
            if self.insertNotices:
                edited += self._notices_business(Path(original))
            else:
                self.process_original(original)

        if originalsChecked == 0:
            if self.insertNotices:
                for path in self.git_ls_files():
                    originalsChecked += 1
                    edited += self._notices_business(path)
            else:
                self.diff_all()

        if self.insertNotices:
            print(f"Checked:{originalsChecked}. Edited:{edited}.")
    
    def _notices_business(self, path):
        if path.is_dir():
            return
        
        noticeOK, linesFound = self._noticesEditor.check(path)

        if noticeOK:
            if self.verbose:
                if linesFound is None:
                    print(
                        f'No notice insertion for suffix "{path.suffix}",'
                        f' skipping "{path}"')
                else:
                    print(f'Notice lines {linesFound} in "{path}"')
            return 0

        if self.verbose or not self.counting:
            print(f'No copyright notices in file "{path}"')
        if self.counting:
            return 1

        editedPath, differences = self._noticesEditor.insert(path)
        overwritten = self._ask_overwrite(editedPath, path, differences)

        if overwritten:
            noticeOK, linesFound = self._noticesEditor.check(path)
            if noticeOK:
                if self.verbose:
                    print('Overwritten file OK.')
            else:
                raise RuntimeError("Overwritten file doesn't have notices.")

        return 1 if overwritten else 0

    def git_ls_files(self):
        # See: https://git-scm.com/docs/git-ls-files  
        # -z switch specifies null-terminators instead of newlines, and verbatim
        # file names for unprintable values.
        with subprocess.Popen(
            ('git', 'ls-files', '-z'), stdout=subprocess.PIPE, text=True
            , cwd=self.top
        ) as gitProcess:
            with gitProcess.stdout as gitOutput:
                name = []
                while True:
                    readChar = gitOutput.read(1)
                    if readChar == "":
                        return
                    if readChar == "\x00":
                        yield Path(self.top, ''.join(name))
                        name = []
                    else:
                        name.append(readChar)

    def process_original(self, original):
        originalPath = Path(original)
        matchCount = 0
        for description, patterns in self._rules.patterns_matched_by(
            originalPath
        ):
            matchCount += 1
            print(f'{original}\nMatches {description}:')
            for pathLeft, path, differences in diff_each(
                glob_each(self._topPath, patterns), originalPath
            ):
                self._ask_overwrite(pathLeft, path, differences)

        if matchCount <= 0:
            print(f'{original}\nNo matches.')
    
    def _ask_overwrite(self, pathSource, pathDestination, differences):
        if differences is None:
            print(f'    Same "{pathDestination}"')
            return None

        print(f'    Different "{pathDestination}"')
        if self.verbose:
            print(''.join(differences))

        while True:
            response = (
                "yes" if self.yes else input('    Overwrite? (Y/n/?)').lower())
            if response == "" or response.startswith("y"):
                print('Overwriting.')
                shutil.copy(pathSource, pathDestination)
                return True
            elif response.startswith("n"):
                print('Keeping')
                return False
            elif response == "?":
                print(''.join(differences))
            else:
                print(f'Unrecognised "{response}". Ctrl-C to quit.')
    
    def diff_all(self, report=sys.stdout):
        for description, paths in self._rules.named_globs():
            pathsFound = None
            pathDifferences = []
            lineDifferences = []
            try:
                for pathLeft, path, differences in diff_each(paths):
                    if pathsFound is None:
                        pathsFound = [pathLeft]
                    pathsFound.append(path)
                    if differences is not None:
                        pathDifferences.append(str(path))
                        lineDifferences.extend(differences)
            except ValueError as error:
                # ToDo sort this out a bit better. Right now, the code gets here
                # if a sub-pattern matches zero or one items. That's different
                # to a "main" pattern matching zero or one items.
                report.write(str(error))
                report.write("\n")
                continue

            pathCount = 0 if pathsFound is None else len(pathsFound)
            if pathCount <= 0:
                report.write(f'Failed, no match for {description}.\n')
            elif pathCount < 2:
                report.write(
                    f'Failed, only one match for {description}:'
                    f' "{pathsFound}"\n')
            elif len(pathDifferences) > 0:
                report.write(f'Differences {description} "{pathsFound[0]}"\n')
                if self.verbose:
                    for difference in lineDifferences:
                        report.write("    " + difference)
                else:
                    for difference in pathDifferences:
                        report.write(f'    "{difference}"\n')
            else:
                report.write(f'OK {pathCount:>2} matches for {description}.\n')

def main(commandLine):
    argumentParser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(__doc__))
    defaultNotices = "copyrightnotices.txt"
    argumentParser.add_argument(
        '-c', '--count', dest='counting', action='store_true', help=
        "Count the number of files that require notice insertion but don't"
        " edit any.")
    argumentParser.add_argument(
        '-i', '--insert-notices', dest='insertNotices', action='store_true'
        , help=
        "Insert notices into files that are in Git but don't have the notices.")
    argumentParser.add_argument(
        '-n', '--notices', default=defaultNotices, type=str, help=
        f'Path to the notices file. Default: "{defaultNotices}"')
    argumentParser.add_argument(
        '--top', type=str, default=str(Path(__file__).parent), help=
        "Top of the source directory tree."
        " Default is the directory that contains this script.")
    argumentParser.add_argument(
        '-v', '--verbose', action='store_true', help="Verbose output.")
    argumentParser.add_argument(
        '--yes', action='store_true', help=
        "Overwrite without prompting. Overridden by --count.")
    argumentParser.add_argument(
        metavar='original', type=str, nargs='*', dest='originals', help=
        "Path of a file to check. Default is to check everything in the"
        " directory tree, or everything in Git.")

    argumentParser.parse_args(commandLine[1:], DuplicatorJob())()

if __name__ == '__main__':
    sys.exit(main(sys.argv))

# ToDo: Mode in which it checks that everything in Git is covered by a rule.