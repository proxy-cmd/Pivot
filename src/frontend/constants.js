import {
  BarChart3,
  Bot,
  Code2,
  FileBarChart2,
  LayoutDashboard,
  Table2,
} from "lucide-react";


export const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export const NAVIGATION_ITEMS = [
  ["Home", LayoutDashboard],
  ["Data", Table2],
  ["Analyze", BarChart3],
  ["Ask Pivot", Bot],
  ["SQL", Code2],
  ["Reports", FileBarChart2],
];

export const DEFAULT_SQL_QUERY = "SELECT * FROM dataset LIMIT 20";

export const ACTIVE_DATASET_KEY = "pivot-active-dataset";
export const PERSONAL_PROFILE_KEY = "pivot-personal-profile";
export const WORKSPACE_SETTINGS_KEY = "pivot-settings";
