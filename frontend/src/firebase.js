import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

const firebaseConfig = {
  apiKey: "AIzaSyDZsKogPpD_G_ZY6fLB3kmuqRWERM0Iuc0",
  authDomain: "smartbuild-faa8f.firebaseapp.com",
  projectId: "smartbuild-faa8f",
  // You can keep only these 3 for Auth.
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
