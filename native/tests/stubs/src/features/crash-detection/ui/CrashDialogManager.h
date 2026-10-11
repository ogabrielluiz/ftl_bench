#pragma once
class CrashDialogManager {
public:
 inline static const CrashDialogManager* existing=nullptr;
 inline static unsigned get_instance_calls=0;
 bool ask=false,choose=false,instructions=false,error=false;
 static const CrashDialogManager* PeekInstanceForBenchmark() { return existing; }
 static CrashDialogManager* GetInstance() { ++get_instance_calls;return nullptr; }
 bool IsAskReportDialogOpen() const { return ask; }
 bool IsChooseDestinationDialogOpen() const { return choose; }
 bool IsInstructionsDialogOpen() const { return instructions; }
 bool IsErrorDialogOpen() const { return error; }
};
