"""Manual test for planner agent tools."""
from file_organization_planner_agent import find_similar_file_reports

if __name__ == "__main__":
    TEST_PATH = "D:/foldermate-test/laya-claim-6830304-2024-01-25.pdf"
    print(find_similar_file_reports(TEST_PATH, top_k=3))
