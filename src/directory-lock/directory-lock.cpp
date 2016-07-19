#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <tchar.h>
#include <iostream>
#include <string>
#include <process.h>
#include <conio.h>

static void markForDeletion(HANDLE file) 
{
	FILE_DISPOSITION_INFO info;
	info.DeleteFileW = TRUE;
	SetFileInformationByHandle(file, FileDispositionInfo, &info, sizeof(info));
}

int _tmain(int argc, TCHAR **argv)
{
	if (argc < 3) {
		std::wstring str(argv[0]);
		std::wcerr << "Usage: "  << str << " <directory name> <command> [args..]\n";
		return 1;
	}
	std::wstring dir(argv[1]);
	std::wstring lockFile = dir + L"\\.directory-lock";
	HANDLE file = CreateFile(lockFile.c_str(), GENERIC_READ | GENERIC_WRITE | DELETE, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
							  nullptr, OPEN_ALWAYS, 0, nullptr);

	if (file == INVALID_HANDLE_VALUE) {
		std::wcerr << "Could not open lock file " << lockFile << '\n';
		exit(1);
	}

	if (GetLastError() != ERROR_ALREADY_EXISTS) { // new file, write message
		std::string message("This file is used to prevent parallel ninja invocations from MSBuild");
		WriteFile(file, message.c_str(), message.length(), nullptr, nullptr);
	}

	OVERLAPPED overlapped;
	memset(&overlapped, 0, sizeof(overlapped));
	LockFileEx(file, LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0, &overlapped);
	
	if (GetFileSize(file, NULL) == 1) {
		// std::wcerr << "Another task failure detected, aborting.\n";
		markForDeletion(file); // probably not necessary, but mark it just in case if for some reason previous delete failed
		CloseHandle(file);
		return 0;
	}

	typedef TCHAR *TSTRING;		
	auto argvIn = new TSTRING[2 + argc - 3];
	argvIn[0] = argv[2];	
	for (int i = 0; i < argc - 3; ++i)
		argvIn[i + 1] = argv[i + 3];
	argvIn[2 + argc - 3 - 1] = NULL;
	auto res = _wspawnvp(_P_WAIT, argv[2], argvIn);
	delete[] argvIn;

	if (res == -1) {
		std::wcerr << "Error: Could not launch " << argv[2] << "\n";
	}

	if (res != 0) {
		// std::wcerr << "Task did fail, deleting lock file to prevent other instances from proceeding.\n";
		
		SetFilePointer(file, 1, 0, FILE_BEGIN);
		SetEndOfFile(file);

		// This task failed, delete file to prevent other lock process currently waiting for lock from executing their tasks
		// This is just to make the build terminate faster
		markForDeletion(file);
	}

	CloseHandle(file);
		
    return res;
}

