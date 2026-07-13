import { Router, type IRouter } from "express";
import healthRouter from "./health";
import miniAppRouter from "./miniApp";

const router: IRouter = Router();

router.use(healthRouter);
router.use(miniAppRouter);

export default router;
