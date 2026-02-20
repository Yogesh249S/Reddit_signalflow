import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:8000/api",
});

export const fetchPosts = () => api.get("/posts/");
export const fetchStats = () => api.get("/stats/");

export default api;