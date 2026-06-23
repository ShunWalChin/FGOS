import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./lib/auth";
import Protected from "./components/Protected";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Kanban from "./pages/Kanban";
import Chat from "./pages/Chat";
import Atendimento from "./pages/Atendimento";
import Campanhas from "./pages/Campanhas";
import Studio from "./pages/Studio";
import Biblioteca from "./pages/Biblioteca";
import Voz from "./pages/Voz";
import Growth from "./pages/Growth";
import Auditoria from "./pages/Auditoria";
import IA from "./pages/IA";
import Memoria from "./pages/Memoria";
import Video from "./pages/Video";
import Social from "./pages/Social";
import Workspace from "./pages/Workspace";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <Protected>
                <Layout />
              </Protected>
            }
          >
            <Route path="/" element={<Dashboard />} />
            <Route path="/crm" element={<Kanban />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/atendimento" element={<Atendimento />} />
            <Route path="/campanhas" element={<Campanhas />} />
            <Route path="/studio" element={<Studio />} />
            <Route path="/biblioteca" element={<Biblioteca />} />
            <Route path="/voz" element={<Voz />} />
            <Route path="/growth" element={<Growth />} />
            <Route path="/auditoria" element={<Auditoria />} />
            <Route path="/ia" element={<IA />} />
            <Route path="/memoria" element={<Memoria />} />
            <Route path="/video" element={<Video />} />
            <Route path="/social" element={<Social />} />
            <Route path="/workspace" element={<Workspace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
