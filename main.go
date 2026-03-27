package main

import (
	"flag"
	"fmt"
	"io/fs"
	"log"
	"os"
	"path/filepath"
	systemtrade "system-trade/system-trade"
	"time"
)

func targetFiles(tDir string) (tFiles []string, err error) {
	err = filepath.Walk(tDir, func(path string, info fs.FileInfo, err error) error {
		if err != nil {
			fmt.Printf("prevent panic by handling failure accessing a path %q: %v\n", path, err)
			return err
		}
		// skip to get the target dir self name
		if path == tDir {
			return nil
		}
		tFiles = append(tFiles, path)
		return nil
	})
	if err != nil {
		return nil, err
	}
	return
}

func isDMAUp(cs systemtrade.CandleSticks, dmaNum, i int) bool {

	// 連続の情報判定のためにfor文
	for j := 0; j < 1; j++ {
		if cs.DMA(10, i-j) <= cs.DMA(10, i-(j+1)) {
			return false
		}
	}

	/*
	*/
	/*
		for j := 0; j < 1; j++ {
			if cs.DMA(25, i-j) <= cs.DMA(25, i-(j+1)) {
				return false
			}
		}
	*/
	/*
			for j := 0; j < 1; j++ {
				if cs.DMA(60, i-j) <= cs.DMA(60, i-(j+1)) {
					return false
				}
			}
	*/

	return true
}

func isDMADown(cs systemtrade.CandleSticks, dmaNum, i int) bool {
	for j := 0; j < 1; j++ {
		if cs.DMA(10, i-j) >= cs.DMA(10, i-(j+1)) {
			return false
		}
	}
	/*
	*/

	/*
		for j := 0; j < 1; j++ {
			if cs.DMA(25, i-j) >= cs.DMA(25, i-(j+1)) {
				return false
			}
		}
	*/
	/*
			for j := 0; j < 1; j++ {
				if cs.DMA(60, i-j) >= cs.DMA(60, i-(j+1)) {
					return false
				}
			}
	*/

	return true
}

func trade(sDate time.Time, cs systemtrade.CandleSticks, lc, lp, tick float64) {

	dmaNum := 10
	skipc := 60
	p := 0.0

	po := systemtrade.Position{Lc: lc, Lp: lp, Tick: tick}
	for i, v := range cs {
		// fmt.Println(v.Date)
		// fmt.Printf("%v", v)
		// for DMA
		if skipc > 0 || v.Date.Before(sDate) {
			skipc--
			continue
		}
		// d := cs.DMA(10, i)
		// fmt.Printf("%v: ", v.Date)
		// fmt.Println(d)
		// fmt.Println(v.Date())
		//10DMAが上向きで、株価のしたひげでも一回でもDMA以下にあって、次の日が高値を超えたら 3% 7%

		wasDMAUp := isDMAUp(cs, dmaNum, i-1)
		wasDMADown := isDMADown(cs, dmaNum, i-1)

		yesterday := cs[i-1]
		wasStockUnderDMA := float64(yesterday.Low) < cs.DMA(dmaNum, i-1)
		wasStockOverDMA := float64(yesterday.High) > cs.DMA(dmaNum, i-1)
		//TODO endにかえる？
		// wasStockUnderDMA := float64(yesterday.End) < cs.DMA(dmaNum, i-1)
		// wasStockOverDMA := float64(yesterday.End) > cs.DMA(dmaNum, i-1)

		if po.IsBuying() {
			_, per, ok := po.Sell(v)
			if ok {
				// fmt.Println("SELL END")
				// fmt.Println(v.Date)
				fmt.Println(per)

			}
			continue
		}
		if po.IsSelling() {
			_, per, ok := po.BuyBack(v)

			if ok {
				//fmt.Println("BUYBUCK END")
				//fmt.Println(v.Date)
				fmt.Println(per)
			}
			continue
		}

		tmpDMA := 25
		_ = tmpDMA
		if wasDMAUp && wasStockUnderDMA {
			// fmt.Println(v.Date)
			// fmt.Println("TIMING!!!")
			if v.High >= yesterday.High {
				p = yesterday.High
				if v.Start > yesterday.High {
					p = v.Start
				}
				po.Buy(p, v)
				// fmt.Printf("Buy: %v: %v\n", v.Date, p)
			}
			/*
				if v.High > cs.DMA(tmpDMA, i-1) {
					p = cs.DMA(tmpDMA, i-1) + 1
					if v.Start > cs.DMA(tmpDMA, i-1) {
						p = v.Start
					}
					po.Buy(p, v)
					fmt.Printf("Buy: %v: %v\n", v.Date, p)
				}
			*/
		}

		if wasDMADown && wasStockOverDMA {
			// fmt.Println(v.Date)
			// fmt.Println("TIMING!!!")
			if v.Low <= yesterday.Low {
				p = yesterday.Low
				if v.Start < yesterday.Low {
					p = v.Start
				}
				po.ShortSell(p, v)
				//fmt.Printf("ShortSell: %v: %v\n", v.Date, p)
			}
			/*
				if v.Low < cs.DMA(tmpDMA, i-1) {
					p = cs.DMA(tmpDMA, i-1) - 1
					if v.Start < cs.DMA(tmpDMA, i-1) {
						p = v.Start
					}
					po.ShortSell(p, v)
					fmt.Printf("ShortSell: %v: %v\n", v.Date, p)
				}
			*/
		}

	}

	systemtrade.Result.Out()
	todayStockUnderDMA := float64(cs[len(cs)-1].Low) < cs.DMA(dmaNum, len(cs)-1)
	todayStockOverDMA := float64(cs[len(cs)-1].High) > cs.DMA(dmaNum, len(cs)-1)
	todayDMAUp := isDMAUp(cs, dmaNum, len(cs)-1)
	todayDMADown := isDMADown(cs, dmaNum, len(cs)-1)

	if todayDMAUp && todayStockUnderDMA {
		fmt.Println(cs[len(cs)-1].Date)
		fmt.Println("[BUY SET TIMING!!!]")

	}
	if todayDMADown && todayStockOverDMA {
		fmt.Println(cs[len(cs)-1].Date)
		fmt.Println("[SHORTSELL SET TIMING!!!]")
	}
}

func main() {
	var (
		tDir = flag.String("tDir", "0", "target folder name")
		lc   = flag.Float64("lc", 0.3, "loss cut %")
		lp   = flag.Float64("lp", 0.07, "limit profit %")
		tick = flag.Float64("tick", 1, "tick")
	)
	flag.Parse()

	if *tDir == "0" {
		os.Exit(1)
	}
	ns, err := targetFiles("./data/" + *tDir)
	if err != nil {
		log.Fatalln(err)
	}
	// fmt.Println(ns)
	vs, err := systemtrade.MakeCandleSticks(ns)
	if err != nil {
		log.Fatal(err)
	}
	// fmt.Println(vs)
	// cnt := 0
	layout := "2006/01/02"
	sDate, _ := time.Parse(layout, "2013/01/01")
	trade(sDate, vs, *lc, *lp, *tick)
}

